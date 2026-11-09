"""Brief 07a2 fix 7: (1) the harness asks for the register map itself; (2) the tests role's self-check before a visit ends;
(3) surviving mutants on the tests role's first repair visit."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from agent.graph.interview import (Interview, SpecOracle, Question, apply_register_answer, ensure_register_question,
                                   is_register_question, register_map_errors, request_needs_register_map)
from agent.graph.run import surviving_mutants_note, selfcheck_tests_role
from flow import verif_gates as G

ROOT = Path(__file__).resolve().parents[2]
T1 = ROOT / "designs" / "t1_dimmer_counter"
SOFTMAX_MD = (ROOT / "benchmark/course/tasks/c15_softmax_unit/spec.md").read_text()


# ---- (1) the register-map question is the harness's ----------------------------------------------------------
def test_a_uart_or_bus_interface_without_offsets_triggers_the_rule() -> None:
    for t in ("A UART command set: W, R, G.", "It has an AXI4-Lite slave port.", "Read the address and the result.",
              "Write the sample over the register window."):
        assert request_needs_register_map(t), t
    assert not request_needs_register_map("The registers are at offsets 0x00 and 0x04.")
    assert not request_needs_register_map("A blinking LED on the board.")


def test_the_harness_adds_the_question_when_the_role_left_it_out() -> None:
    spec = {"registers": {"map": [{"name": "ID", "offset": 0, "access": "RO", "reset": "0x534D4158"}]}, "open_questions": []}
    assert register_map_errors(SOFTMAX_MD, spec), "the gate must still fail an unasked map"
    out, added = ensure_register_question(SOFTMAX_MD, spec)
    assert added and is_register_question(out["open_questions"][-1]["question"])
    q = out["open_questions"][-1]
    assert q["default"].startswith("ID: offset 0x00, RO, reset 0x534D4158") and q["reason"]
    assert register_map_errors(SOFTMAX_MD, out) == []
    assert spec["open_questions"] == []                       # the input is not changed


def test_no_second_question_when_the_role_asked_one() -> None:
    asked = {"open_questions": [{"question": "What is the register map (offsets)?", "default": "x", "reason": "y"}]}
    assert ensure_register_question(SOFTMAX_MD, asked)[1] is False
    resolved = {"resolved_questions": [{"question": "register map offsets?", "answer": "A: offset 0x00, RW, reset 0: x"}]}
    assert ensure_register_question(SOFTMAX_MD, resolved)[1] is False
    assert ensure_register_question("A blinking LED.", {})[1] is False


def test_stub_oracle_answers_the_added_question_with_the_whole_map_and_fix_6_applies(tmp_path: Path) -> None:
    hidden = tmp_path / "hidden.yaml"
    hidden.write_text(yaml.safe_dump({"registers": {"map": [
        {"name": "X0", "offset": 0, "access": "RW", "reset": 0, "bits": "[7:0] lane"},
        {"name": "GO", "offset": 16, "access": "WO", "reset": 0, "bits": "[0] start"}]}}))
    calls: list = []
    oracle = SpecOracle(hidden, lambda s, u: calls.append(u) or {"answer": "not specified", "quote": None})
    role_spec = {"registers": {"map": [{"name": "ID", "offset": 0, "access": "RO", "reset": 0},
                                       {"name": "CTRL", "offset": 4, "access": "RW", "reset": 0}]}, "open_questions": []}
    spec, added = ensure_register_question(SOFTMAX_MD, role_spec)
    assert added
    iv = Interview()
    for o in spec["open_questions"]:
        iv.ask(Question(id="q1", text=o["question"], default=o["default"], reason=o["reason"]), oracle)
    assert calls == [] and iv.questions[0].status == "answered" and iv.questions[0].by == "oracle"   # no model call
    spec = apply_register_answer(iv.resolve_into(spec))
    assert sorted(e["offset"] for e in spec["registers"]["map"]) == [0, 16]
    assert next(e for e in spec["registers"]["map"] if e["offset"] == 0)["name"] == "X0"
    assert register_map_errors(SOFTMAX_MD, spec) == []


# ---- (2) the tests role's self-check -------------------------------------------------------------------------
def _patched(monkeypatch, edit) -> None:
    plan = yaml.safe_load((T1 / "verif" / "testplan.yaml").read_text())
    spec = yaml.safe_load((T1 / "spec.yaml").read_text())
    edit(plan)
    real = yaml.safe_load
    monkeypatch.setattr(G.yaml, "safe_load", lambda t: plan if "fpga-design-agent/testplan" in t
                        else spec if "fpga-design-agent/spec" in t else real(t))


def test_a_clean_testplan_has_no_self_check_problem(monkeypatch) -> None:
    _patched(monkeypatch, lambda p: None)
    probs = G.static_check(T1, "V3")
    assert not any(x.startswith(("V0", "V1")) for x in probs)


def test_formal_for_a_bench_test_is_caught_before_the_visit_ends(monkeypatch) -> None:
    def edit(p):
        for e in p["proof"]:
            if e["method"] == "simulation":
                e["method"], e["artefact"] = "formal", e["artefact"]       # softmax run 2: a bench test declared formal
                break
    _patched(monkeypatch, edit)
    probs = G.static_check(T1, "V2")
    assert any("proof_references_resolve" in x and "simulation" in x for x in probs), probs


def test_missing_random_test_bins_and_cover_props_are_caught(monkeypatch) -> None:
    def edit(p):
        for r in p["requirements"]:
            r["bins"], r["cover_props"] = [], []
    _patched(monkeypatch, edit)
    probs = G.static_check(T1, "V3")
    assert any("no functional bins planned" in x for x in probs) and any("no cover properties planned" in x for x in probs)
    assert not any("cover" in x for x in G.static_check(T1, "V2"))            # a V2 run does not need them


def test_the_self_check_repairs_then_stops(tmp_path: Path, monkeypatch) -> None:
    class Rt:
        design = tmp_path
        visit = 3
        cfg = type("C", (), {"verif_level": "V3"})()
    outputs = [["V1 x: bad"], ["V1 x: bad"], []]
    monkeypatch.setattr(G, "static_check", lambda d, level="V3": outputs.pop(0))
    asked: list = []
    left = selfcheck_tests_role(Rt(), lambda extra: asked.append(extra), passes=2)
    assert left == [] and asked == [["V1 x: bad"], ["V1 x: bad"]]
    rows = [json.loads(x) for x in (tmp_path / "build/verif/selfcheck.jsonl").read_text().splitlines()]
    assert [r["problems"] for r in rows] == [["V1 x: bad"], ["V1 x: bad"], []] and rows[0]["visit"] == 3


def test_the_self_check_gives_up_after_its_passes_and_never_raises(tmp_path: Path, monkeypatch) -> None:
    class Rt:
        design = tmp_path
        visit = 1
        cfg = type("C", (), {"verif_level": "V3"})()
    monkeypatch.setattr(G, "static_check", lambda d, level="V3": ["V1 x: bad"])
    asked: list = []
    assert selfcheck_tests_role(Rt(), lambda e: asked.append(e), passes=2) == ["V1 x: bad"] and len(asked) == 2

    def boom(d, level="V3"):
        raise RuntimeError("no plan")
    monkeypatch.setattr(G, "static_check", boom)
    assert selfcheck_tests_role(Rt(), lambda e: asked.append(e), passes=2) == []


# ---- (3) surviving mutants on the first repair visit ---------------------------------------------------------
def test_surviving_mutants_note(tmp_path: Path) -> None:
    assert surviving_mutants_note(tmp_path) == ""
    m = tmp_path / "build" / "verif"
    m.mkdir(parents=True)
    (m / "mutation.json").write_text(json.dumps({
        "score_pct": 54.55, "killed": 6, "evaluated": 11,
        "survivor_text": [f"rtl/core.sv:{i}: `+` -> `-`" for i in range(7)], "timed_out_text": ["rtl/core.sv:90: `<` -> `<=`"]}))
    note = surviving_mutants_note(tmp_path)
    assert "54.55%" in note and "6 of 11" in note
    assert note.count("\n- ") == 8 and "rtl/core.sv:6" in note and "timed out, counts as not killed: rtl/core.sv:90" in note
    (m / "mutation.json").write_text(json.dumps({"score_pct": 100, "survivor_text": [], "timed_out_text": []}))
    assert surviving_mutants_note(tmp_path) == ""
