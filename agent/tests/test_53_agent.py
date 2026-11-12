"""Brief 53, the agent side: the clarify check rejects vague and compound requirements, the tests role is told to tag,
the harness records the traceability matrix, and the review index shows it."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from agent.graph import review as rv
from agent.graph import run as R
from agent.graph.spec_schema import requirement_quality_errors, validate

ROOT = Path(__file__).resolve().parents[2]
MINI = ROOT / "flow" / "tests" / "fixtures" / "trace53" / "mini"


def _spec(*texts: str) -> dict:
    return {"requirements": [{"id": f"REQ-{i + 1:02d}", "text": t, "proof": ["simulation"]} for i, t in enumerate(texts)]}


def test_compound_and_vague_requirements_are_rejected():
    errs = requirement_quality_errors(_spec(
        "COUNT wraps modulo 65536 on an up press",                                 # fine
        "The counter counts up and down; a release makes no press",                # compound: ';'
        "The display shows COUNT, and the LEDs show the duty",                     # compound: ', and' + a second verb
        "The UART should respond quickly",                                         # vague: should, quickly
        "Handles errors",                                                          # vague and too short
        "The design closes timing at 100 MHz. Power stays below 1 W",              # compound: two sentences
        "Latency is at most 3 clocks and throughput is one sample per clock",      # compound without a comma
        "The counter counts up when UP is pressed and down when DOWN is pressed",  # compound without a comma
        "Latency is approx. 3 clocks"))                                            # vague: approx
    text = "\n".join(errs)
    assert "REQ-01" not in text
    assert "REQ-02 is compound (';'" in text and "REQ-03 is compound (', and'" in text
    assert "REQ-04 is vague ('quickly', 'should')" in text
    assert "REQ-05 is vague ('handles')" in text and "REQ-05 is too short" in text
    assert "REQ-06 is compound ('a second sentence'" in text
    assert "REQ-07 is compound ('and'" in text and "REQ-08 is compound ('and'" in text
    assert "REQ-09 is vague ('approx')" in text


def test_good_requirements_pass_the_quality_check():
    """Review finding 5: lists, 'may not', short exact statements and a trailing reference are not rejected."""
    assert requirement_quality_errors(_spec(
        "The LED outputs R, G, and B are driven from the PWM duty register",
        "The UART runs at 115200 baud, 8 data bits, no parity, and one stop bit",
        "The core may not assert valid while reset is high",
        "LED0 mirrors SW0",
        "The window follows the register map per spec v1.2. See section 3",
        "The display lights exactly one digit at a time, in order, showing COUNT and the duty in hex",
        # re-review N1: a conjunction inside a condition is one requirement
        "The output is high when A is high and B is low",
        "GRANT goes to requester 0 only while REQ[0] is set and LOCK is clear",
        "COUNT increments when UP is pressed and DOWN is not pressed",
        "A press counts only if the button is held for 10 ms and is then released",
        "The FIFO stops accepting data until the reader has drained it and EMPTY is high")) == []
    # a condition does not hide a second statement after it
    assert requirement_quality_errors(_spec("TX is idle when EN is low, and the LED is lit"))


def test_the_clarify_gate_applies_the_quality_check_and_validate_does_not():
    """validate() also checks the benchmark's frozen hidden specs, so the quality check sits in the clarify gate only."""
    import inspect
    spec = {"name": "x", "top": "x", "ports": [1], "clocks": [1], "reset": {"a": 1}, "behaviour": {"g": ["a"]},
            "registers": {"map": [{"name": "R"}]}, "timing": {"latency": {}}, "requirements": _spec(
                "COUNT wraps; COUNT holds")["requirements"]}
    assert not any("compound" in e for e in validate(spec))
    assert "validate(spec) + requirement_quality_errors(spec)" in inspect.getsource(R)


def test_role_prompts_ask_for_atomic_requirements_and_tags():
    assert "ONE checkable statement" in R.PROMPTS["clarify"]
    assert "# req: REQ-01, REQ-02" in R.PROMPTS["tests"] and "structural" in R.PROMPTS["tests"]


def test_trace_record_and_review_index(tmp_path):
    d = tmp_path / "mini"
    shutil.copytree(MINI, d)
    run = d / "build" / "verif" / "sim" / "seed1"
    run.mkdir(parents=True)
    cases = "".join(f'<testcase classname="mini_bench" name="{n}"></testcase>'
                    for n in ("counts_and_wraps", "holds_when_disabled", "reset_mid_count", "zz_export"))
    (run / "results.xml").write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>")
    rec = R.trace_record(d, tmp_path)
    assert set(rec["defer"]) == {"analysis", "hardware", "coverage"}
    assert rec["gates"]["artefacts_cite_requirements"] and not rec["gates"]["requirements_verified"]   # no formal run
    t = json.loads((d / "build" / "trace" / "trace.json").read_text())
    assert t["schema"] == "fpga-design-agent/trace/v1" and (d / "build" / "trace" / "trace.md").is_file()
    page = rv.write_index(d, [], None).read_text()
    assert "<h2>Traceability matrix</h2>" in page and "REQ-01" in page and "requirements_verified" in page
    assert "not a claim of compliance" in page


def test_review_index_without_a_matrix(tmp_path):
    page = rv.write_index(tmp_path, [], None).read_text()
    assert "No traceability matrix yet" in page


def test_a_stale_requirement_stays_stale_until_reverified(tmp_path):
    """Review finding 2: the record runs at the gate and again at the review; a changed requirement must stay stale on
    both until its evidence changes, not clear itself on the second record."""
    d = tmp_path / "mini"
    shutil.copytree(MINI, d)
    run = d / "build" / "verif" / "sim" / "seed1"
    run.mkdir(parents=True)
    cases = "".join(f'<testcase classname="mini_bench" name="{n}"></testcase>'
                    for n in ("counts_and_wraps", "holds_when_disabled", "reset_mid_count", "zz_export"))
    (run / "results.xml").write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>")
    assert R.trace_record(d, tmp_path)["changed"]["stale"] == []
    spec = d / "spec.yaml"
    spec.write_text(spec.read_text().replace("while enable is low", "while enable is low or reset is high"))
    assert R.trace_record(d, tmp_path)["changed"]["stale"] == ["REQ-02"]          # node_gate
    assert R.trace_record(d, tmp_path)["changed"]["stale"] == ["REQ-02"]          # node_review, same stage
    bench = d / "tests" / "mini_bench.py"
    bench.write_text(bench.read_text().replace("async def holds_when_disabled(dut):\n    pass",
                                               "async def holds_when_disabled(dut):\n    pass  # now also under reset"))
    assert R.trace_record(d, tmp_path)["changed"]["stale"] == []                  # evidence changed: re-verified
    assert R.trace_record(d, tmp_path)["changed"]["stale"] == []
