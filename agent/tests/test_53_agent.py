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
        "The display shows COUNT, and the LEDs show the duty",                     # compound: ', and'
        "The UART should respond quickly",                                         # vague: should, quickly
        "Handles errors",                                                          # vague and too short
        "The design closes timing at 100 MHz. Power stays below 1 W"))             # compound: two sentences
    text = "\n".join(errs)
    assert "REQ-01" not in text
    assert "REQ-02 is compound (';'" in text and "REQ-03 is compound (', and'" in text
    assert "REQ-04 is vague ('quickly', 'should')" in text
    assert "REQ-05 is vague ('handles')" in text and "REQ-05 is too short" in text
    assert "REQ-06 is compound" in text


def test_validate_carries_the_quality_errors():
    spec = {"name": "x", "top": "x", "ports": [1], "clocks": [1], "reset": {"a": 1}, "behaviour": {"g": ["a"]},
            "registers": {"map": [{"name": "R"}]}, "timing": {"latency": {}}, "requirements": _spec(
                "COUNT wraps; COUNT holds")["requirements"]}
    assert any("REQ-01 is compound" in e for e in validate(spec))


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
