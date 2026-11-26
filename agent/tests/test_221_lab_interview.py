"""Brief 221: the lab questions of the interview, how their answers are recorded, their risk class, and the requirements-report column.

No instrument and no model: the lab is built in memory, the interview bookkeeping is the real one."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from agent.graph import lab_interview as LI
from agent.graph import requirements as RQ
from agent.graph.interview import Interview, Question
from flow import requirements_report as rr
from flow import traceability as tr
from hil import lab as L
from hil import lab_bringup as B
from hil.tests.test_221_lab import P1, WIRED, counter, lab_of, p1_spec


@pytest.fixture(autouse=True)
def _no_owner_profile(monkeypatch):
    monkeypatch.setenv(L.ENV_FILE, "none")


def needs():
    return L.needs_from_spec(p1_spec())


def test_no_lab_asks_once_and_only_a_person():
    q = LI.questions(L.Lab(), needs(), person=True)
    assert len(q) == 1 and q[0]["question"].startswith("[lab:record]") and q[0]["default"].startswith("No: on-chip measurement only") and q[0]["reason"]
    assert LI.questions(L.Lab(), needs(), person=False) == []                      # an oracle or off run behaves as before
    assert LI.questions(L.Lab(), needs(), person=True, asked="x [lab:record] y") == []
    assert LI.questions(L.Lab(), [], person=True) == []                            # nothing an instrument could check: nothing to ask
    declined = L.Lab(declined=True)
    assert LI.questions(declined, needs(), person=True) == []


def test_a_gap_question_per_onboarded_capable_unwired_instrument_with_a_default_and_a_reason():
    q = LI.questions(lab_of(counter()), needs())
    assert len(q) == 1
    t = q[0]["question"]
    assert t.startswith("[lab:connect:counter:REQ-13]") and "25 MHz" in t and "independent check beside" in t and "which channel probes which pin" in t
    assert q[0]["default"].startswith("not connected") and "wrong pin" in q[0]["reason"]
    assert LI.questions(lab_of(counter(), conns=WIRED), needs()) == []             # already wired: no gap
    assert LI.questions(lab_of(counter(onboarded=False)), needs()) == []           # never onboarded: offered in the plan only
    assert LI.questions(lab_of(counter()), needs(), asked=t) == []                 # asked once


def test_the_questions_join_the_spec_like_the_protocol_intake_and_do_not_stop_a_standard_run(tmp_path):
    spec = p1_spec()
    spec, tags = LI.ensure_lab_questions(tmp_path, spec, lab=lab_of(counter()))
    assert tags == ["[lab:connect:counter:REQ-13]"] and spec["open_questions"][-1]["question"].startswith(tags[0])
    again, tags2 = LI.ensure_lab_questions(tmp_path, spec, lab=lab_of(counter()))
    assert tags2 == [] or again["open_questions"].count(spec["open_questions"][-1]) == 1
    k = RQ.classify(spec["open_questions"][-1]["question"])
    assert k.cls == "low" and k.rule == "lab-bench"                                # it names a frequency and a pin, which would be high without the tag
    iv = Interview(level="standard")
    o = spec["open_questions"][-1]
    q = iv.ask(Question(id="q1", text=o["question"], default=o["default"], reason=o["reason"]), None)
    assert q.status == "defaulted" and iv.unresolved() == []
    strict = Interview(level="strict").ask(Question(id="q1", text=o["question"], default=o["default"], reason=o["reason"]), None)
    assert strict.status == "unresolved"                                           # at strict every question is answered or waived


def test_answer_forms():
    assert LI.parse_answer("counter: A -> pin C3") == [("counter", "A", "pin C3")]
    assert LI.parse_answer("m2k: DIO0 -> C3; m2k: DIO1 -> led[0]") == [("m2k", "DIO0", "C3"), ("m2k", "DIO1", "led[0]")]
    assert LI.parse_answer("not connected") == [] and LI.parse_answer("No") == []
    assert LI.parse_answer("the counter is on A") is None and LI.parse_answer("") is None


def resolved(answer, tag="[lab:connect:counter:REQ-13]", status="answered", by="human"):
    return [{"question": f"{tag} blah", "answer": answer, "status": status, "by": by, "default_reason": "r"}]


def test_a_connect_answer_is_written_to_the_design_lab_file_with_provenance_and_changes_the_plan(tmp_path):
    lab = lab_of(counter())
    rec = LI.record_answers(tmp_path, resolved("counter: A -> pin C3"), lab)
    assert rec["problems"] == [] and rec["connections"][0]["probes"] == "pin C3"
    doc = yaml.safe_load((tmp_path / "lab.yaml").read_text())
    c = doc["connections"][0]
    assert c["provenance"] == {"source": "interview", "by": "human", "status": "answered", "answer": "counter: A -> pin C3", "reason": "r"}
    prof = tmp_path / "prof.yaml"
    prof.write_text(yaml.safe_dump({"instruments": [counter()]}))
    after = L.load(tmp_path, prof)
    assert after.problems == [] and L.plan(after, needs())["requirements"][0]["chosen"]["method"] == "scripted"
    again = LI.record_answers(tmp_path, resolved("counter: A -> pin C3"), lab)           # idempotent
    assert len(again["connections"]) == 1


def test_a_default_or_a_misformed_or_unknown_answer_records_nothing_and_says_why(tmp_path):
    lab = lab_of(counter())
    assert LI.record_answers(tmp_path, resolved("not connected: on-chip", status="defaulted", by="default"), lab)["connections"] == []
    assert not (tmp_path / "lab.yaml").exists()
    rec = LI.record_answers(tmp_path, resolved("it is on channel A"), lab)
    assert "is not '<instrument>: <CHANNEL> -> <pin>'" in rec["problems"][0] and not (tmp_path / "lab.yaml").exists()
    rec = LI.record_answers(tmp_path, resolved("counter: Z9 -> pin C3"), lab)
    assert "no channel 'Z9'" in rec["problems"][0]
    rec = LI.record_answers(tmp_path, resolved("scope: A -> pin C3"), lab)
    assert "no instrument 'scope'" in rec["problems"][0]
    assert json.loads((tmp_path / "build" / "lab" / "answer_problems.json").read_text())


def test_declining_the_record_question_is_written_so_it_is_not_asked_again(tmp_path):
    rec = LI.record_answers(tmp_path, resolved("No: on-chip measurement only for this design.", tag="[lab:record]", status="defaulted", by="default"), L.Lab())
    assert rec["declined"] and L.load(tmp_path).declined
    assert LI.questions(L.load(tmp_path), needs(), person=True) == []


# ---- the requirements report ------------------------------------------------------------------------------------------------------------
def report_for(tmp_path, plan_lab=None, results=None):
    d = tmp_path / "design"
    (d / "build" / "lab").mkdir(parents=True)
    if plan_lab is not None:
        (d / "build" / "lab" / "plan.json").write_text(json.dumps(L.plan(plan_lab, needs())))
    if results is not None:
        (d / "build" / "lab" / "results.json").write_text(json.dumps(results))
    t = tr.build(P1, None, defer=("analysis", "hardware", "coverage"))
    return rr.build_report(d, t, p1_spec(), "", {}), d


def row13(rep):
    return next(r for r in rep["requirements"] if r["id"] == "REQ-13")


def test_without_a_lab_plan_the_report_is_exactly_as_before(tmp_path):
    rep, _ = report_for(tmp_path)
    assert "lab" not in row13(rep) and "instrument (" not in rr.to_markdown(rep) and "instrument: none" not in rr.to_markdown(rep)


def test_an_on_chip_only_plan_says_so_and_why(tmp_path):
    rep, _ = report_for(tmp_path, lab_of(counter(onboarded=False)))
    assert row13(rep)["lab"]["status"] == "none"
    assert "instrument: none, on-chip only (counter: available after onboarding)" in rr.to_markdown(rep)


def test_the_c3_frequency_row_gains_an_independent_instrument_check_beside_the_on_chip_count(tmp_path):
    rep, _ = report_for(tmp_path, lab_of(counter(), conns=WIRED))
    r = row13(rep)
    assert r["lab"]["status"] == "pending" and r["result"] == "pending"
    md = rr.to_markdown(rep)
    assert "hardware: pending<br>instrument (counter A on pin C3, scripted): pending" in md


def run_result(value, mode="run", result=None):
    return {"mode": mode, "evidence": mode == "run", "rows": [{"step": "req_13_counter", "requirement": "REQ-13", "kind": "measure", "instrument": "counter",
                                                                "result": result or ("dry_run" if mode == "dry_run" else "pass"), "value": value, "unit": "Hz", "error_ppm": 8.0}]}


def test_a_failed_independent_check_fails_the_requirement_and_a_dry_run_changes_nothing(tmp_path):
    lab = lab_of(counter(), conns=WIRED)
    bad, _ = report_for(tmp_path / "a", lab, run_result(25.2e6, result="fail"))
    assert row13(bad)["result"] == "fail" and "independent instrument check failed" in row13(bad)["reason"] and bad["failed"] == 1
    dry, _ = report_for(tmp_path / "b", lab, run_result(25e6, mode="dry_run"))
    assert row13(dry)["lab"]["status"] == "dry_run" and row13(dry)["result"] == "pending"
    assert "dry run against a mock, not evidence" in rr.to_markdown(dry) and "read 25" not in rr.to_markdown(dry)
    ok, _ = report_for(tmp_path / "c", lab, run_result(25.0002e6))
    assert "instrument (counter A on pin C3, scripted): pass read 25.0002 MHz" in rr.to_markdown(ok)
    assert row13(ok)["lab"]["status"] == "pass" and row13(ok)["result"] == "pending"      # the on-chip count is still to come; the instrument pass alone does not pass the row


def test_a_real_run_that_used_a_mock_instrument_is_still_not_evidence(tmp_path):
    res = run_result(25.0002e6)
    res["rows"][0]["mock"] = True
    rep, _ = report_for(tmp_path, lab_of(counter(), conns=WIRED), res)
    assert row13(rep)["lab"]["status"] == "dry_run"
