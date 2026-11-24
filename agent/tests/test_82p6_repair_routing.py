"""Brief 82P6: P1 (repair-hint routing), P3 (diagnosing stop reasons, the RTL role's last message), the clarify-exit constants check
and owner routing of a persisting CONST-ID-01. Planted cases and a replay of the recorded 82P4 B r2 / B r3 stage-2 failures; no
model call."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.graph import repair, run as gr
from agent.graph.stages import MACHINE, classify, constants_stage, exit_check, route_failure
from flow import derived_constants as DC

S2 = MACHINE[2]
FIX = Path(__file__).parent / "fixtures" / "b82p6_replay_evidence.json"
FF = {"test": "test_reset_and_scratch", "message": ["AssertionError: status 2 expected 0"], "where": "bench.py:261", "cause": [], "frames": []}
V2 = {"failing_tests": {"pass": False, "value": ["seed1:b.test_a"], "threshold": []},
      "constrained_random_test_ran": {"pass": False, "value": False, "threshold": True, "why": "no passing test with 'random' in its name"},
      "assertions_bound_zero_failures": {"pass": False, "value": [], "threshold": "bound", "why": "a test failed in some seed"}}


def ev(**kw):
    e = {"lint": {"ok": True}, "standards_fails": [], "constants": None, "contract": {"ok": True},
         "simulate": {"ok": False, "first_failure": FF, "text": "[first failure] t"},
         "verif": {"reached": "V1", "first_failed": "V2", "stages": {"V2": {"checks": dict(V2)}}}, "verif_level": "V2", "spec_test": {}}
    e.update(kw)
    return e


# ---- P1 -------------------------------------------------------------------------------------------------------------------
def test_p1_consequence_checks_do_not_make_the_verifier_an_owner():
    o, sig = repair.stage2_owners(ev(), repeat=0)
    assert list(o) == ["rtl"] and "tests:" not in sig                    # before: the Verifier owned the V2 consequences


def test_p1_the_bench_owner_gets_the_repeat_hint_with_the_failing_assertion():
    o, sig0 = repair.stage2_owners(ev(), repeat=1)
    assert list(o) == ["tests", "rtl"]
    assert "survived a repair" in o["tests"][0] and "status 2 expected 0" in o["tests"][0] and "test_reset_and_scratch" in o["tests"][0]
    assert repair.stage2_owners(ev(), repeat=0)[1] == sig0               # the signature ignores the hint


def test_p1_the_hint_is_added_even_when_the_verifier_owns_something_else():
    untraced = {"V1": {"checks": {"untraced_items": {"value": ["behaviour.a[0]"], "threshold": [], "pass": False}}}}
    e = ev(verif={"reached": "V0", "first_failed": "V1", "stages": untraced})
    o, _ = repair.stage2_owners(e, repeat=1)
    assert len(o["tests"]) == 2 and "behaviour.a[0]" in o["tests"][0] and "survived a repair" in o["tests"][1]
    assert "status 2 expected 0" in o["tests"][1]


def test_p1_a_real_plan_gap_still_goes_to_the_verifier_while_the_simulation_fails():
    v = {"V2": {"checks": {**V2, "formal_tasks_not_passing": {"pass": False, "value": ["x=absent"], "threshold": []}}}}
    o, _ = repair.stage2_owners(ev(verif={"reached": "V1", "first_failed": "V2", "stages": v}), repeat=0)
    assert "tests" in o and "formal_tasks_not_passing" in o["tests"][0] and "constrained_random" not in o["tests"][0]


def test_p1_when_the_simulation_passes_the_random_test_check_is_the_verifiers():
    e = ev(simulate={"ok": True})
    o, _ = repair.stage2_owners(e, repeat=0)
    assert list(o) == ["tests"] and "constrained_random_test_ran" in o["tests"][0]


def _first_failure(text: str) -> dict:
    lines = text.splitlines()
    return {"test": lines[0].replace("[first failure] ", "").strip(), "message": [l.strip() for l in lines[1:] if l.strip().startswith("AssertionError")][:3],
            "where": None, "cause": [], "frames": [l.strip() for l in lines if 'File "' in l]}


@pytest.mark.parametrize("tag", ["B_r2", "B_r3"])
def test_p1_replay_of_the_recorded_82p4_failures_routes_the_hint_to_the_bench_owner(tag):
    rec = json.loads(FIX.read_text())[tag]
    assert rec["verif"]["V2"]["constrained_random_test_ran"]["pass"] is False          # as recorded
    for s in rec["sim_failures"]:
        e = ev(simulate={"ok": False, "first_failure": _first_failure(s), "text": s},
               verif={"reached": rec["verif"]["reached"], "first_failed": "V2", "stages": {"V2": {"checks": rec["verif"]["V2"]}}})
        o0, _ = repair.stage2_owners(e, repeat=0)
        o1, _ = repair.stage2_owners(e, repeat=1)
        assert list(o0) == ["rtl"]                                                      # the consequence checks are covered
        assert list(o1) == ["tests", "rtl"] and "survived a repair" in o1["tests"][0]
        assert "AssertionError" in o1["tests"][0]


# ---- P3 -------------------------------------------------------------------------------------------------------------------
def _state(**kw):
    e = ev()
    owners, sig = repair.stage2_owners(e, repeat=2)
    s = {"evidence": e, "owners": owners, "sig": sig, "repeat": 2, "fails": ["simulate not passing"]}
    s.update(kw)
    return s


def test_p3_the_stop_reason_names_gate_role_assertion_and_keeps_the_prefix():
    why, d = repair.stop_diagnosis(2, 6, _state())
    assert why.startswith("stage 2 visited more than 6 times")           # the handover (document.py) matches this prefix
    assert "simulate" in why and "rtl role" in why and "status 2 expected 0" in why and "3 consecutive visits" in why
    assert d["gates"] == ["simulate"] and d["roles"] == ["rtl"] and d["last_failing_assertion"].startswith("test_reset_and_scratch")
    assert d["same_signature_visits"] == 3 and d["owners_last_visit"] == ["model", "rtl", "tests"]


def test_p3_other_gates_and_other_stages():
    c = {"findings": [{"code": "CONST-ID-01", "blocking": True, "where": "rtl/x.sv", "message": "m"}]}
    e = ev(simulate={"ok": True}, constants=c, verif={"reached": "V2", "stages": {}})
    o, sig = repair.stage2_owners(e)
    why, d = repair.stop_diagnosis(2, 6, {"evidence": e, "owners": o, "sig": sig, "repeat": 0, "fails": []})
    assert "derived constants" in why and d["gates"] == ["derived constants"] and "consecutive" not in why
    why3, d3 = repair.stop_diagnosis(3, 4, {"fails": ["constants CONST-CLK-01 x.xdc: create_clock -period 8"], "evidence": {}})
    assert why3.startswith("stage 3 visited more than 4 times") and "CONST-CLK-01" in why3


def test_p3_node_work_stops_with_the_diagnosis_and_the_detail(tmp_path):
    rt = SimpleNamespace(cfg=SimpleNamespace(run_limits={"visits_per_stage": 4}), run_id="x")
    gr._RT["x"] = rt
    try:
        out = gr.node_work({"run_id": "x", "stage": 2, "visits": {"2": 6}, **_state()})
    finally:
        gr._RT.pop("x")
    assert out["stop"].startswith("stage 2 visited more than 6 times; last failing gate: simulate")
    assert out["stop_detail"]["limit"] == 6 and out["visits"]["2"] == 7


def test_p3_the_rtl_roles_last_message_is_kept_truncated(tmp_path):
    rt = SimpleNamespace(last_role_message={}, session=SimpleNamespace(stage="rtl-design-creation"), visit=3)
    gr.record_role_message(rt, "rtl", "x" * 10 + "  ")
    assert rt.last_role_message["rtl"] == {"stage": "rtl-design-creation", "visit": 3, "text": "x" * 10}
    gr.record_role_message(rt, "rtl", "head" + "m" * 5000 + "TAIL")
    t = rt.last_role_message["rtl"]["text"]
    assert t.startswith("head") and t.endswith("TAIL") and "characters cut" in t and len(t) < gr.ROLE_MESSAGE_KEEP + 80
    gr.record_role_message(rt, "rtl", "")                                # an empty message keeps the earlier one
    assert rt.last_role_message["rtl"]["text"].endswith("TAIL")
    assert gr._last_ai_text({"messages": [SimpleNamespace(content=[{"type": "text", "text": "done"}])]}) == "done"
    assert gr._last_ai_text(None) == ""


# ---- clarify exit ----------------------------------------------------------------------------------------------------------
SPEC_MD = 'Register 0 is the identification word 0x55445031. The design ID is "UEP1".\n'
ROOT = Path(__file__).resolve().parents[2]


def spec_design(tmp: Path, design_id, period=10, spec_md=SPEC_MD) -> Path:
    d = tmp / "d"
    d.mkdir()
    (d / "spec.md").write_text(spec_md)
    y = f"name: d\nboard: nexys_a7_100t\nclocks:\n- name: CLK100MHZ\n  port: CLK100MHZ\n  period_ns: {period}\nparameters:\n  DESIGN_ID: {design_id}\n"
    (d / "spec.yaml").write_text(y)
    return d


def test_clarify_exit_fails_on_the_planted_82p5_design_id(tmp_path):
    d = spec_design(tmp_path, 1430540337)                                 # 0x55445031: the 82P5 planted run's spec.yaml
    fs = DC.spec_yaml_findings(d, ROOT)
    assert [f["code"] for f in fs] == ["CONST-ID-03"] and fs[0]["blocking"]
    assert "0x55455031" in fs[0]["message"] and "1430605873" in fs[0]["message"] and "0x55445031" in fs[0]["message"]


@pytest.mark.parametrize("val", ["1430605873", "0x55455031", "'0x5545_5031'"])
def test_clarify_exit_accepts_the_right_id_in_any_spelling(tmp_path, val):
    assert DC.spec_yaml_findings(spec_design(tmp_path, val), ROOT) == []


def test_clarify_exit_checks_the_board_clock_and_ignores_other_clocks(tmp_path):
    d = spec_design(tmp_path, 1430605873, period=8)                       # the 82P5 clock plant
    fs = DC.spec_yaml_findings(d, ROOT)
    assert [f["code"] for f in fs] == ["CONST-CLK-02"] and "set period_ns to 10" in fs[0]["message"]
    (d / "spec.yaml").write_text((d / "spec.yaml").read_text().replace("port: CLK100MHZ", "port: GEN_CLK"))
    assert DC.spec_yaml_findings(d, ROOT) == []                           # not the board's oscillator port: no claim


def test_clarify_exit_makes_no_claim_without_a_quoted_id_or_a_parameter(tmp_path):
    assert DC.spec_yaml_findings(spec_design(tmp_path, 1, spec_md="no id quoted here\n"), ROOT) == []
    d = tmp_path / "e"
    d.mkdir()
    (d / "spec.md").write_text(SPEC_MD)
    (d / "spec.yaml").write_text("name: x\nparameters:\n  WIDTH: 8\n")
    assert DC.spec_yaml_findings(d, ROOT) == []
    (d / "spec.yaml").write_text(": not yaml [")
    assert DC.spec_yaml_findings(d, ROOT) == []


def test_clarify_exit_gate_wrapper_blocks_and_never_raises(tmp_path):
    d = spec_design(tmp_path, 1430540337)
    rt = SimpleNamespace(design=d, session=SimpleNamespace(root=ROOT), cfg=SimpleNamespace(board="nexys_a7_100t"))
    assert [f["code"] for f in gr.spec_constants_findings(rt)] == ["CONST-ID-03"]
    assert gr.spec_constants_findings(SimpleNamespace(design=None, session=None, cfg=None)) == []


def test_clarify_exit_finding_fails_the_spec_signed_gate_with_the_message(tmp_path):
    d = spec_design(tmp_path, 1430540337)
    f = DC.spec_yaml_findings(d, ROOT)[0]
    errs = ["constants " + f"{f['code']} {f['where']}: {f['message']}"]
    ok, fails = exit_check(MACHINE[0], {"spec": {"name": "d"}, "signed_off": True, "spec_errors": errs})
    assert not ok and "CONST-ID-03" in fails[0] and "0x55455031" in fails[0]
    assert exit_check(MACHINE[0], {"spec": {"name": "d"}, "signed_off": True, "spec_errors": []})[0]


# ---- owner routing of a persisting CONST-ID-01 -----------------------------------------------------------------------------------
def routed_design(tmp: Path, spec_has_it=True) -> Path:
    d = tmp / "r"
    (d / "rtl").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "spec.md").write_text(SPEC_MD)
    (d / "rtl" / "top.sv").write_text("module top; fpga_shell #(.DESIGN_ID(32'h55445031)) u (.clk(c)); parameter [31:0] R0_ID = 32'h55445031; endmodule\n")
    (d / "model.py").write_text("class Model:\n    def __init__(self, DESIGN_ID=1430540337, R0_ID=0x55445031): pass\n")
    (d / "tests" / "bench.py").write_text("DESIGN_ID = 0x55445031\nR0 = 0x55445031\n")
    (d / "spec.yaml").write_text(("parameters:\n  DESIGN_ID: 1430540337\n" if spec_has_it else "parameters:\n  DESIGN_ID: 1430605873\n"))
    return d


def test_holders_are_the_artefacts_that_write_the_wrong_value_as_a_design_id(tmp_path):
    d = routed_design(tmp_path)
    f = DC.derive(d, tmp_path)["findings"][0]
    assert f["code"] == "CONST-ID-01"
    got = {h["role"]: (h["file"], h["line"]) for h in f["holders"]}
    assert set(got) == {"spec", "model", "tests", "rtl"}
    assert got["model"] == ("model.py", "2") and got["tests"] == ("tests/bench.py", "1")        # the R0 lines are not design IDs


def test_first_visit_goes_to_the_rtl_only_and_a_persisting_finding_to_every_holder(tmp_path):
    d = routed_design(tmp_path, spec_has_it=False)
    fs = DC.derive(d, tmp_path)["findings"]
    base = {"lint": {"ok": True}, "contract": {"ok": True}, "simulate": {"ok": True}, "arch_approval": {"ok": True},
            "standards": {"rules": []}, "verif": {"reached": "V3", "stages": {}}, "verif_level": "V1"}
    first = {**base, "constants": {"findings": fs}}
    assert list(repair.stage2_owners(first)[0]) == ["rtl"]
    later = {**base, "constants": {"findings": fs, "persisted": True}}
    o, sig = repair.stage2_owners(later)
    assert list(o) == ["model", "tests", "rtl"]
    assert "model.py line 2" in o["model"][0] and "0x55455031" in o["model"][0] and "0x55445031" in o["model"][0]
    assert "tests/bench.py line 1" in o["tests"][0]
    assert "rtl/" not in o["model"][0] and "fpga_shell" not in o["model"][0]           # the Modeller stays blind to the RTL
    assert "CONST-ID-01" in o["rtl"][0] and "constants" in sig


def test_a_wrong_value_held_by_spec_yaml_routes_to_the_clarify_stage(tmp_path):
    fs = DC.derive(routed_design(tmp_path / "a", spec_has_it=True), tmp_path)["findings"]
    ok, fails = constants_stage({"findings": fs})
    assert not ok and classify(S2, fails) == "rtl"                         # first sighting: the RTL role
    ok, fails = constants_stage({"findings": fs, "persisted": True})
    assert "held by spec.yaml" in fails[0] and classify(S2, fails) == "spec" and route_failure(S2, "spec") == 0
    fs2 = DC.derive(routed_design(tmp_path / "b", spec_has_it=False), tmp_path)["findings"]
    assert classify(S2, constants_stage({"findings": fs2, "persisted": True})[1]) == "rtl"   # spec.yaml is right: not the clarify stage's


def test_the_second_sighting_of_the_same_wrong_value_is_marked_persisted():
    f = {"code": "CONST-ID-01", "blocking": True, "bound": 1, "holders": []}
    other = {"code": "CONST-ID-01", "blocking": True, "bound": 2, "holders": []}
    assert gr.mark_persisted({"findings": [f]}, {"findings": [f]})["persisted"] is True
    assert "persisted" not in gr.mark_persisted(None, {"findings": [f]})
    assert "persisted" not in gr.mark_persisted({"findings": [f]}, {"findings": [other]})          # a different wrong value: new
    assert "persisted" not in gr.mark_persisted({"findings": [f]}, {"findings": []})
    adv = {"code": "CONST-ID-02", "blocking": False, "bound": 1}
    assert "persisted" not in gr.mark_persisted({"findings": [adv]}, {"findings": [adv]})


# ---- events for the run record -----------------------------------------------------------------------------------------------
def test_events_say_which_change_fired():
    ev_list: list = []
    repair.stage2_owners(ev(), repeat=1, events=ev_list)
    kinds = [e["event"] for e in ev_list]
    assert "p1_consequences_covered" in kinds and "p1_hint_sent" in kinds
    assert ev_list[kinds.index("p1_hint_sent")]["test"] == "test_reset_and_scratch"
    quiet: list = []
    repair.stage2_owners(ev(simulate={"ok": True}), repeat=0, events=quiet)
    assert quiet == []


def test_routing_events_are_written_and_summarised(tmp_path):
    rt = SimpleNamespace(run_dir=tmp_path, session=SimpleNamespace(stage="rtl-design-creation"), visit=2)
    gr.log_routing_event(rt, "p1_hint_sent", repeat=1, test="t")
    gr.log_routing_event(rt, "clarify_constants_check", findings=[], failed=False)
    got = gr.routing_events(rt)
    assert [e["event"] for e in got] == ["p1_hint_sent", "clarify_constants_check"] and got[0]["visit"] == 2 and got[0]["repeat"] == 1
    assert gr.routing_events(SimpleNamespace(run_dir=tmp_path / "none")) == []


def test_holder_patterns_read_hex_decimal_and_sized_literals(tmp_path):
    d = tmp_path / "h"
    (d / "tests").mkdir(parents=True)
    (d / "model.py").write_text("DESIGN_ID = 32'h5544_5031\n")
    (d / "tests" / "b.py").write_text("design id 1430540337\nDESIGN_ID = 0x55455031\n")
    hs = {h["role"]: h["file"] for h in DC.wrong_value_holders(d, 0x55445031)}
    assert hs == {"model": "model.py", "tests": "tests/b.py"}               # the right value 0x55455031 is not a holder
