"""Brief 210: the requirements verification report (flow/requirements_report.py), on the recorded t1_dimmer_counter run.

T1 has 11 requirements and 14 requirement-and-method rows (the committed reference simulation run, formal status files written here, and
the f0b bring-up record). Cases: a clean report with its pending analysis rows, a pending hardware row that becomes pass or fail by
regenerating from the bring-up JSON alone, a failed row, a requirement the report marks failed because a fix broke it, and the origin of
each requirement (a line of the request, an answered question, a default with its class, a waiver, the Clarifier's own reading, recorded or not)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from flow import requirements_report as rr
from flow import traceability as tr

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
T1 = ROOT / "designs" / "t1_dimmer_counter"
REF = HERE / "data" / "ref_t1_sim"
BRINGUP = ROOT / "results" / "f0b" / "t1_dimmer_counter_bringup.json"


def formal_dir(tmp: Path) -> Path:
    f = tmp / "formal"
    for job in ("debounce", "scan"):
        for task in tr.sby_tasks(T1 / "verif" / "formal" / f"{job}.sby"):
            (f / f"{job}_{task}").mkdir(parents=True)
            (f / f"{job}_{task}" / "status").write_text("PASS 0\n")
    return f


def trace(tmp: Path, hw: Path | None, defer=("analysis",)) -> dict:
    return tr.build(T1, REF, formal=formal_dir(tmp), hw=hw, defer=defer + (("hardware",) if hw is None else ()))


def report(t: dict, state: dict | None = None) -> dict:
    spec = yaml.safe_load((T1 / "spec.yaml").read_text())
    return rr.build_report(T1, t, spec, (T1 / "spec.md").read_text(), state)


def by_id(rep: dict) -> dict:
    return {r["id"]: r for r in rep["requirements"]}


def test_the_fixture_has_the_rows_the_tests_rely_on(tmp_path):
    t = trace(tmp_path, BRINGUP)
    assert len(t["requirements"]) == 11 and sum(len(r["methods"]) for r in t["requirements"]) == 14


def test_a_clean_report_counts_passed_pending_and_failed(tmp_path):
    rep = report(trace(tmp_path, BRINGUP))
    assert (rep["total"], rep["passed"], rep["pending"], rep["failed"]) == (11, 9, 2, 0)           # REQ-06 and REQ-07 (analysis) await the build
    assert rep["headline"] == "9 of 11 requirements verified and passed; 2 pending; 0 failed"
    r = by_id(rep)
    assert r["REQ-06"]["result"] == "pending" and "analysis evidence not produced yet" in r["REQ-06"]["reason"]
    assert r["REQ-08"]["result"] == "pass"
    assert rep["unverified"] == []


def test_a_pending_hardware_row_is_pending_until_the_bringup_exists(tmp_path):
    rep = report(trace(tmp_path, None))
    assert (rep["passed"], rep["pending"], rep["failed"]) == (7, 4, 0)
    r = by_id(rep)
    assert r["REQ-08"]["result"] == "pending" and r["REQ-11"]["result"] == "pending"
    assert "hardware evidence not produced yet" in r["REQ-08"]["reason"]


def test_a_failed_bringup_step_is_a_failed_row(tmp_path):
    bad = json.loads(BRINGUP.read_text())
    bad["steps"]["ila_captures"]["pass"] = False
    bad["pass"] = False
    p = tmp_path / "bad_bringup.json"
    p.write_text(json.dumps(bad))
    rep = report(trace(tmp_path, p))
    r = by_id(rep)
    assert r["REQ-11"]["result"] == "fail" and r["REQ-08"]["result"] == "pass"
    assert (rep["passed"], rep["pending"], rep["failed"]) == (8, 2, 1)
    assert rep["headline"].endswith("1 failed")


def test_a_requirement_a_fix_broke_is_failed_with_the_reason(tmp_path):
    state = {"level": "loose", "conflicts": [{"requirement": "REQ-01", "code": "RPT-LL-02", "fix_kind": "pipeline", "level": "loose",
                                             "action": "proceeded", "requirement_text": "x", "why": "the fix adds registers"}]}
    rep = report(trace(tmp_path, BRINGUP), state)
    r = by_id(rep)["REQ-01"]
    assert r["result"] == "fail" and "RPT-LL-02" in r["reason"] and "the run went ahead" in r["reason"]
    assert rep["failed"] == 1 and rep["passed"] == 8
    assert rep["conflicts"][0]["requirement"] == "REQ-01"
    assert "A fix that conflicts with a requirement" in rr.to_markdown(rep)


def test_every_row_has_links_to_its_evidence(tmp_path):
    rep = report(trace(tmp_path, BRINGUP))
    r = by_id(rep)["REQ-01"]
    ev = [e for m in r["methods"] for e in m["evidence"]]
    assert ev and all(e["link"] for e in ev) and any(e["link"].endswith(".py#L" + e["link"].split("#L")[-1]) for e in ev)
    hw = by_id(rep)["REQ-08"]["methods"][0]["evidence"][0]
    assert hw["link"].endswith("t1_dimmer_counter_bringup.json") and hw["result"] == "pass"
    md = rr.to_markdown(rep)
    assert "| REQ-01 |" in md and "[t1_cocotb." in md and md.count("\n| REQ-") == 11


# ---- where a requirement came from ------------------------------------------------------------------------------------------------------
REQUEST = "# A counter\nThe counter wraps modulo 65536 at both ends.\nThe LEDs show the count in binary.\n"
SPEC = {"resolved_questions": [
    {"question": "What debounce interval qualifies a button press?", "answer": "10 ms", "status": "defaulted", "by": "default", "risk": "high"},
    {"question": "How many digits does the display scan?", "answer": "8 digits, one at a time", "status": "answered", "by": "oracle"},
    {"question": "Which pin drives the buzzer?", "answer": "pin H17 (LVCMOS33)", "status": "waived", "by": "default", "risk": "high",
     "waiver": {"who": "Alex", "when": "2026-11-25", "why": "the schematic says H17"}}]}


def test_origin_is_a_request_line_an_answered_question_a_default_a_waiver_or_the_agents_reading():
    og = lambda text, **kw: rr.origin_of({"id": "R", "text": text, **kw}, SPEC, REQUEST)             # noqa: E731
    a = og("The counter wraps modulo 65536 at both ends")
    assert (a["kind"], a["detail"], a["unconfirmed"]) == ("spec", "your request, near line 2", False)
    b = og("The display scans 8 digits, one at a time")
    assert b["kind"] == "answered" and "oracle" in b["detail"] and not b["unconfirmed"]
    c = og("A button press is accepted after the 10 ms debounce interval")
    assert (c["kind"], c["risk"], c["unconfirmed"]) == ("default", "high", True)
    d = og("The buzzer is driven from pin H17 with LVCMOS33")
    assert d["kind"] == "waiver" and "Alex" in d["detail"] and d["unconfirmed"]
    e = og("The design answers a read of address 0x20 with the version")
    assert e["kind"] == "unrecorded" and not e["unconfirmed"]          # nothing says it is a guess, and nothing says it is not
    assert og("x", origin={"kind": "agent", "detail": "inferred"})["unconfirmed"]
    f = og("anything", origin={"kind": "answered", "detail": "q7"})
    assert f["kind"] == "answered" and f["detail"] == "q7"


def test_a_pass_on_an_unconfirmed_default_is_marked_and_counted(tmp_path):
    t = trace(tmp_path, BRINGUP)
    spec = yaml.safe_load((T1 / "spec.yaml").read_text())
    spec["requirements"][0]["origin"] = {"kind": "default", "detail": "a default: debounce", "risk": "high"}
    rep = rr.build_report(T1, t, spec, "", None)
    r = by_id(rep)["REQ-01"]
    assert r["result"] == "pass" and r["rests_on_unconfirmed"] and r["high_risk_default"]
    assert rep["unconfirmed_passes"] >= 1
    md = rr.to_markdown(rep)
    assert "[not confirmed, high risk]" in md and "[on an unconfirmed default]" in md and "rest on a default or an assumption you did not confirm" in md


def test_the_assumptions_of_the_spec_are_in_the_report(tmp_path):
    spec = yaml.safe_load((T1 / "spec.yaml").read_text())
    spec["resolved_questions"] = SPEC["resolved_questions"]
    rep = rr.build_report(T1, trace(tmp_path, BRINGUP), spec, "", None)
    md = rr.to_markdown(rep)
    assert "## Assumptions you did not confirm" in md and "debounce interval" in md and "waived by Alex" in md and "oracle" not in md.split("Assumptions")[1]


# ---- regenerating after a board run -------------------------------------------------------------------------------------------------------
def design_copy(tmp: Path) -> Path:
    d = tmp / "t1_dimmer_counter"
    shutil.copytree(T1, d)
    sim = d / "build" / "verif" / "sim"
    shutil.copytree(REF, sim)
    shutil.copytree(formal_dir(tmp), d / "build" / "verif" / "formal")
    return d


def test_regenerating_after_the_board_run_turns_pending_rows_into_pass_without_another_edit(tmp_path):
    d = design_copy(tmp_path)
    first = rr.refresh(d)
    assert (first["passed"], first["pending"]) == (7, 4) and by_id(first)["REQ-08"]["result"] == "pending"
    assert "pending" in (d / rr.REPORT).read_text() and (d / "build" / "trace" / "trace.json").is_file()
    (d / "build" / "bringup").mkdir()
    shutil.copy(BRINGUP, d / "build" / "bringup" / "t1_dimmer_counter_bringup.json")      # the board run's record, and nothing else
    second = rr.refresh(d)
    assert (second["passed"], second["pending"], second["failed"]) == (9, 2, 0)
    assert by_id(second)["REQ-08"]["result"] == "pass" and by_id(second)["REQ-11"]["result"] == "pass"
    assert second["headline"] in (d / rr.REPORT).read_text()
    saved = json.loads(d.joinpath(*rr.JSON_REL).read_text())
    assert saved["headline"] == second["headline"] and saved["schema"] == rr.SCHEMA


def test_the_command_takes_the_bringup_json_by_flag_and_fails_on_a_failed_row(tmp_path, capsys):
    d = design_copy(tmp_path)
    bad = json.loads(BRINGUP.read_text())
    bad["steps"]["uart_tests"]["pass"] = False
    bad["pass"] = False
    p = tmp_path / "board.json"
    p.write_text(json.dumps(bad))
    rc = rr.main([str(d), "--hw", str(p)])
    out = capsys.readouterr().out
    assert rc == 1 and "REQ-08" in out and "fail" in out
    assert by_id(json.loads(d.joinpath(*rr.JSON_REL).read_text()))["REQ-08"]["result"] == "fail"


# ---- the handover shows the assumptions and links the report ---------------------------------------------------------------------------------
def test_the_handover_schema_takes_the_assumptions_and_the_report_link_and_the_readme_renders_them():
    from flow import handover as H
    h = H.load(T1)
    assert H._validate(h) == []
    h["requirements_report"] = "REQUIREMENTS_REPORT.md"
    h["assumptions"] = [{"question": "What debounce interval qualifies a press?", "risk": "high", "used": "10 ms", "how": "defaulted: nobody answered"}]
    assert H._validate(h) == []
    readme = H.render_readme(h, T1, {}, {})
    assert "## Assumptions you did not confirm" in readme and "| high | What debounce interval qualifies a press? | 10 ms |" in readme
    assert "[REQUIREMENTS_REPORT.md](REQUIREMENTS_REPORT.md)" in readme
    agent = H.render_agent(h, T1)
    assert "## assumptions_not_confirmed" in agent and "[high] What debounce interval" in agent
    h["assumptions"][0]["risk"] = "severe"
    assert H._validate(h)                                     # a class outside low, medium, high is refused
    plain = H.render_readme(H.load(T1), T1, {}, {})
    assert "Assumptions you did not confirm" not in plain       # a handover without them renders as before


def test_the_doc_draft_carries_the_assumptions_from_spec_yaml(tmp_path):
    from agent.graph import document
    d = tmp_path / "d"
    d.mkdir()
    spec = {"resolved_questions": [{"question": "Which clock is clk_sys?", "answer": "10 MHz", "status": "defaulted", "by": "default", "default_reason": "x"}]}
    f = document.requirements_fields(d, spec)
    assert "requirements_report" not in f and f["assumptions"][0]["risk"] == "high"
    (d / "REQUIREMENTS_REPORT.md").write_text("# r\n")
    assert document.requirements_fields(d, spec)["requirements_report"] == "REQUIREMENTS_REPORT.md"
    assert document.requirements_fields(d, {}) == {"requirements_report": "REQUIREMENTS_REPORT.md"}
    assert document.requirements_fields(tmp_path / "none", {}) == {}
