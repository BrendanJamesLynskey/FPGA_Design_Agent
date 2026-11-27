"""Brief 214: per-stage model routing with escalation, and k-way attempts. Offline: no CLI call, no model, no network.
The k-way tests drive ``_kway_work`` with recorded gate results (stub work and gate nodes that edit real files in a real design directory)."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from agent import __main__ as cli
from agent.claude_code_arm import arm
from agent.core.runner import RunResult
from agent.core.session import ROOT
from agent.graph import run as gr
from agent.graph.stages import MACHINE
from agent.models import routing as rg

T1 = ROOT / "designs" / "t1_dimmer_counter"
S2 = "rtl-design-creation"


class Runner:
    def run(self, kind, argv, cwd, env=None, timeout=600):
        return RunResult(0, "ok", "", 0.0)


@pytest.fixture
def runs(monkeypatch):
    d = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", d)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def mk(runs, **kw):
    kw = {"harness": "claude_code", "cc_model": "claude-sonnet-5-5", "cc_effort": "medium", **kw}
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", **kw)
    rt = gr.new_runtime(cfg, lambda *a, **k: None, runner=Runner())
    (rt.design / "spec.yaml").write_text("name: x\n")
    return rt


def enter(rt, n):
    rt.meter.start_stage(MACHINE[n].limits)
    rt.session.stage = MACHINE[n].name


def calls(monkeypatch):
    got = []
    monkeypatch.setattr(arm, "run_subagent_cc", lambda rt_, plan: got.append((plan["role"], plan["model"], plan["effort"])) or {})
    return got


# ---- 1. the table ---------------------------------------------------------------------------------------------------------------------------

def test_visit_kinds_come_from_the_failure_texts():
    assert rg.visit_kind("rtl", None, False) == "write"
    assert rg.visit_kind("rtl", ["[lint] x", "[design standards] y"], True) == "repair_lint"
    assert rg.visit_kind("rtl", ["[lint] x", "[simulate] y"], True) == "repair"
    assert rg.visit_kind("rtl", [], True) == "repair"


def test_the_table_row_decides_and_no_row_is_standard():
    assert rg.table_tier("rtl", S2, "repair_lint")[0] == "cheap"
    assert rg.table_tier("rtl", S2, "repair")[0] == "standard"
    assert rg.table_tier("rtl", "constraints", "repair_lint")[0] == "standard"
    assert rg.table_tier("tests", S2, "repair")[0] == "standard"


def test_every_table_row_names_a_known_stage_role_kind_and_tier():
    from agent.graph.role_models import ROLE_NAMES
    names = {s.name for s in MACHINE} | {"*"}
    for role, stage, kind, tier, why in rg.ROUTING_TABLE:
        assert role in ROLE_NAMES and stage in names and kind in (*rg.KINDS, "*") and tier in rg.TIERS and why


def test_standard_leaves_the_resolved_spec_untouched_and_chat_kinds_are_skipped():
    spec = {"harness": "claude_code", "model": "claude-sonnet-5-5", "effort": "medium"}
    r = rg.route(spec, "rtl", S2, "repair", 0, "claude_code")
    assert r["spec"] == spec and not r["changed"] and r["tier"] == "standard"
    r = rg.route({"harness": "deepagents", "model": "m", "effort": None}, "rtl", S2, "repair_lint", 3, "openrouter")
    assert not r["changed"] and r["skipped"] == "kind openrouter" and r["spec"]["model"] == "m"


def test_cheap_and_strong_tiers_are_claude_code_models_never_a_network_opus():
    assert rg.TIERS["cheap"]["model"] == "claude-haiku-5-5" and rg.TIERS["strong"]["model"] == "claude-opus-5-5"
    spec = {"harness": "claude_code", "model": "claude-sonnet-5-5", "effort": "medium"}
    assert rg.route(spec, "rtl", S2, "repair_lint", 0, "claude_code")["spec"]["model"] == "claude-haiku-5-5"
    assert rg.route(spec, "rtl", S2, "repair_lint", 0, "anthropic_api")["spec"] == spec          # the API kind is not routed (Opus is blocked there)


# ---- 2. escalation ----------------------------------------------------------------------------------------------------------------------------

def test_the_same_failure_on_two_visits_escalates_the_next_visit_and_a_change_resets_it():
    f = rg.FailureStreak()
    assert f.see(2, "") == 0
    assert f.see(2, "rtl:lint") == 1
    assert f.streak(2) == 1 and rg.route({"model": "s", "effort": "m"}, "rtl", S2, "repair_lint", 1, "claude_code")["tier"] == "cheap"
    assert f.see(2, "rtl:lint") == 2
    r = rg.route({"model": "claude-sonnet-5-5", "effort": "medium"}, "rtl", S2, "repair_lint", f.streak(2), "claude_code")
    assert r["escalated"] and r["tier"] == "strong" and r["spec"]["model"] == "claude-opus-5-5"
    assert f.see(2, "rtl:sim:x") == 1                       # a different failure: back to the table
    assert f.see(3, "") == 0 and f.streak(2) == 1            # stages are counted apart
    assert f.failed_visits(2) == 3


def test_failure_signature_ignores_numbers_and_spacing_but_stage_2_uses_its_own():
    a = rg.failure_signature(["lint failed at line 12:  port 0x1F"])
    assert a == rg.failure_signature(["lint failed at line 345: port 0x2A"])
    assert rg.failure_signature(["x"], "rtl:lint") == "rtl:lint"


def test_routing_off_is_todays_models_and_records_nothing_extra(runs, monkeypatch):
    rt = mk(runs)
    got = calls(monkeypatch)
    enter(rt, 2)
    rt.route_reasons = ["[lint] x"]
    gr.run_subagent(rt, "rtl", "p", (), True)
    assert got == [("rtl", "claude-sonnet-5-5", "medium")]
    assert "routing" not in gr.role_usage(rt)[0] and "cost_routing" not in gr.summary(rt, {"history": []})


def test_routing_on_sends_a_lint_repair_to_the_cheap_tier_and_records_it(runs, monkeypatch):
    rt = mk(runs, routing="on")
    got = calls(monkeypatch)
    enter(rt, 2)
    rt.route_reasons = ["[lint] x"]
    gr.run_subagent(rt, "rtl", "p", (), True)
    rt.route_reasons = ["[simulate] y"]
    gr.run_subagent(rt, "rtl", "p", (), True)
    gr.run_subagent(rt, "model", "p", (), False)
    assert got == [("rtl", "claude-haiku-5-5", "low"), ("rtl", "claude-sonnet-5-5", "medium"), ("model", "claude-sonnet-5-5", "medium")]
    rows = gr.role_usage(rt)
    assert [r["routing"]["tier"] for r in rows] == ["cheap", "standard", "standard"]
    assert rows[0]["model"] == "claude-haiku-5-5" and rows[0]["routing"]["base_model"] == "claude-sonnet-5-5" and rows[0]["routing"]["reason"]
    assert not rows[0]["stage_override"]
    ev = [e for e in gr.routing_events(rt) if e["event"] == "route"]
    assert len(ev) == 1 and ev[0]["tier"] == "cheap" and ev[0]["changed"]
    s = gr.summary(rt, {"history": []})["cost_routing"]
    assert s["per_tier"]["cheap"]["calls"] == 1 and s["per_tier"]["standard"]["calls"] == 2 and s["escalated_calls"] == 0


def test_routing_on_escalates_after_two_visits_with_the_same_failure(runs, monkeypatch):
    rt = mk(runs, routing="on")
    got = calls(monkeypatch)
    enter(rt, 2)
    rt.streak = rg.FailureStreak()
    for _ in range(3):
        rt.streak.see(2, "rtl:lint")
    rt.route_reasons = ["[lint] x"]
    gr.run_subagent(rt, "rtl", "p", (), True)
    assert got == [("rtl", "claude-opus-5-5", "medium")]
    r = gr.role_usage(rt)[0]
    assert r["routing"]["escalated"] and r["routing"]["tier"] == "strong" and r["routing"]["streak"] == 3
    assert gr.summary(rt, {"history": []})["cost_routing"]["escalated_calls"] == 1


def test_a_deep_agents_role_is_not_routed_and_says_so(runs, monkeypatch):
    import deepagents
    rt = mk(runs, routing="on", harness="deepagents")

    class Stub:
        def invoke(self, *a, **k):
            return {"files": {}}
    monkeypatch.setattr(deepagents, "create_deep_agent", lambda **kw: Stub())
    monkeypatch.setattr(gr, "chat_model", lambda client, *a, **k: object())
    enter(rt, 2)
    rt.route_reasons = ["[lint] x"]
    gr.run_subagent(rt, "rtl", "p", (), True)
    r = gr.role_usage(rt)[0]
    assert r["routing"]["skipped"].startswith("kind ") and not r["routing"]["changed"] and r["model"] == rt.cfg.model


def test_the_flags_default_to_off_and_round_trip(runs):
    a = cli.build_parser().parse_args(["run", "x.md"])
    assert (a.routing, a.kway) == ("off", 0)
    a = cli.build_parser().parse_args(["run", "x.md", "--routing", "on", "--kway", "3"])
    assert (a.routing, a.kway) == ("on", 3)
    rt = mk(runs, routing="on", kway=3)
    c = cli.config_from_json(json.loads((rt.run_dir / "config.json").read_text()))
    assert (c.routing, c.kway) == ("on", 3)
    old = json.loads((rt.run_dir / "config.json").read_text())
    old.pop("routing"), old.pop("kway")
    c = cli.config_from_json(old)                                    # an older record resumes with both off
    assert (c.routing, c.kway) == ("off", 0)


# ---- 3. k-way ---------------------------------------------------------------------------------------------------------------------------------

def row(i, gates=5, findings=1, luts=None, ind="none"):
    return {"candidate": i, "gates_passed": gates, "gates": 9, "findings": findings, "luts": luts, "independent": ind}


def test_an_independent_verdict_outranks_the_designers_own_gates():
    rows = [row(1, gates=8, ind="fail"), row(2, gates=5, ind="pass"), row(3, gates=9, ind="none")]
    c = rg.select_candidate(rows)
    assert c["candidate"] == 2 and c["decided_by"] == "independent verdict" and not c["own_gates_only"]
    assert rg.select_candidate([row(1, 8, ind="fail"), row(2, 5, ind="none")])["candidate"] == 2      # a failing independent check ranks last


def test_ties_go_to_gates_then_findings_then_luts_then_the_lowest_number():
    assert rg.select_candidate([row(1, gates=4), row(2, gates=6)]) == {"candidate": 2, "decided_by": "gates passed", "own_gates_only": True}
    assert rg.select_candidate([row(1, findings=3), row(2, findings=1)])["decided_by"] == "findings"
    c = rg.select_candidate([row(1, luts=900), row(2, luts=400), row(3, luts=None)])
    assert c["candidate"] == 2 and c["decided_by"] == "LUTs"
    assert rg.select_candidate([row(2), row(1)]) == {"candidate": 1, "decided_by": "candidate number", "own_gates_only": True}
    assert rg.select_candidate([row(7)])["decided_by"] == "only candidate"


def test_gates_passed_counts_each_gate_alone_and_the_independent_verdict_reads_the_evidence():
    st = MACHINE[2]
    ev = {"lint": {"ok": True}, "simulate": {"ok": False}, "contract": {"ok": True}, "arch_approval": {"ok": True}, "standards": {"rules": []},
          "constants": {"findings": []}, "verif": {"reached": "V2"}, "verif_level": "V2", "report_gates": None, "trace": {}}
    ok, total = rg.gates_passed(st, ev)
    assert total == len(st.gates) and 0 < ok < total
    assert rg.independent_verdict({"regrade": {"status": "pass"}}) == ("pass", "regrade")
    assert rg.independent_verdict({"regrade": {"status": "pass"}, "spec_test": {"verdict": "design_wrong"}}) == ("fail", "spec_test")
    assert rg.independent_verdict({"regrade": {"status": "not_applicable"}}) == ("none", None)
    assert rg.luts_of({"gates_base": {"stages": {"post_synth": {"utilization": {"lut": 321}}}}}) == 321 and rg.luts_of({}) is None


def test_sandbox_isolation_restore_returns_the_exact_snapshot_and_never_touches_build(tmp_path):
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "build").mkdir()
    (d / "rtl" / "a.sv").write_text("A")
    (d / "build" / "keep.txt").write_text("B")
    names = rg.snapshot_design(d, tmp_path / "base")
    assert names == ["rtl/a.sv"]
    (d / "rtl" / "a.sv").write_text("EDIT")
    (d / "rtl" / "new.sv").write_text("NEW")
    rg.restore_design(d, tmp_path / "base")
    assert (d / "rtl" / "a.sv").read_text() == "A" and not (d / "rtl" / "new.sv").exists() and (d / "build" / "keep.txt").read_text() == "B"


def stub_kway(rt, monkeypatch, plan):
    """work: attempt i writes rtl/top.sv = plan[i]['text']; gate: returns plan[i]'s fails and evidence. Records the file seen at the start of each attempt."""
    seen, order = [], []

    def work(state):
        i = rt.attempt
        order.append(i)
        top = rt.design / "rtl" / "top.sv"
        seen.append(top.read_text() if top.exists() else None)
        top.parent.mkdir(exist_ok=True)
        top.write_text(plan[i]["text"])
        return {"visits": {**(state.get("visits") or {}), "2": 3}, "note": "", **({"stop": plan[i]["stop"]} if plan[i].get("stop") else {})}

    def gate(state):
        i = rt.attempt
        return {"evidence": plan[i].get("ev", {}), "fails": plan[i]["fails"]}
    monkeypatch.setattr(gr, "node_work", work)
    monkeypatch.setattr(gr, "node_gate", gate)
    return seen, order


def test_kway_runs_k_attempts_from_one_snapshot_keeps_the_best_and_logs_every_candidate(runs, monkeypatch):
    rt = mk(runs, kway=3)
    rt.streak = rg.FailureStreak()
    for _ in range(2):
        rt.streak.see(2, "rtl:lint")
    (rt.design / "rtl").mkdir(exist_ok=True)
    (rt.design / "rtl" / "top.sv").write_text("BASE")
    ok_ev = {"lint": {"ok": True}, "simulate": {"ok": True}, "contract": {"ok": True}, "arch_approval": {"ok": True}, "standards": {"rules": []},
             "constants": {"findings": []}, "verif": {"reached": "V2"}, "verif_level": "V2", "report_gates": None, "trace": {}}
    plan = {1: {"text": "ONE", "fails": ["lint not passing"], "ev": {}},
            2: {"text": "TWO", "fails": ["simulate not passing"], "ev": {"lint": {"ok": True}, "contract": {"ok": True}}},
            3: {"text": "THREE", "fails": [], "ev": ok_ev}}
    seen, order = stub_kway(rt, monkeypatch, plan)
    out = gr._kway_work(rt, {"stage": 2, "visits": {"2": 2}, "fails": ["lint not passing"], "run_id": rt.run_id}, 2)
    assert order == [1, 2, 3] and seen == ["BASE", "BASE", "BASE"]               # every attempt started from the same files
    assert (rt.design / "rtl" / "top.sv").read_text() == "THREE"                  # the best candidate is what stays
    rows = [json.loads(x) for x in (rt.run_dir / "kway.jsonl").read_text().splitlines()]
    cands = [r for r in rows if "candidate" in r]
    assert [c["candidate"] for c in cands] == [1, 2, 3] and cands[2]["passes"] and not cands[0]["passes"]
    assert rows[-1]["chosen"] == 3 and rows[-1]["own_gates_only"] is True
    assert out["visits"]["2"] == 3 and rt.attempt == 0 and rt.kway_rounds[2] == 1
    ev = [e["event"] for e in gr.routing_events(rt)]
    assert ev.count("kway_start") == 1 and ev.count("kway_chosen") == 1
    s = gr.summary(rt, {"history": []})["cost_routing"]
    assert s["kway"] == 3 and len([c for c in s["kway_candidates"] if "candidate" in c]) == 3


def test_a_stop_in_the_first_attempt_leaves_the_design_as_it_was(runs, monkeypatch):
    rt = mk(runs, kway=2)
    rt.streak = rg.FailureStreak()
    (rt.design / "rtl").mkdir(exist_ok=True)
    (rt.design / "rtl" / "top.sv").write_text("BASE")
    stub_kway(rt, monkeypatch, {1: {"text": "HALF", "fails": [], "stop": "budget: run usd"}})
    out = gr._kway_work(rt, {"stage": 2, "visits": {"2": 2}, "fails": ["x"], "run_id": rt.run_id}, 2)
    assert out["stop"] == "budget: run usd" and (rt.design / "rtl" / "top.sv").read_text() == "BASE"


def test_node_work_starts_k_way_only_after_two_failed_visits_once_and_never_inside_an_attempt(runs, monkeypatch):
    rt = mk(runs, kway=3)
    fired = []
    def fake(rt_, state, n):
        fired.append(n)
        rt_.kway_rounds[n] = rt_.kway_rounds.get(n, 0) + 1
        return {"visits": {"2": 3}, "note": ""}
    monkeypatch.setattr(gr, "_kway_work", fake)
    monkeypatch.setattr(gr, "permission_entry", lambda *a: None)
    monkeypatch.setattr(gr, "stage2_plan", lambda rt_, state: {})
    monkeypatch.setattr(gr, "follow_spec_language", lambda rt_: None)
    monkeypatch.setattr(gr, "role_allowed", lambda *a: ())
    monkeypatch.setattr(gr.arch_mod, "approval_status", lambda d: (True, ""))
    base = {"stage": 2, "run_id": rt.run_id, "fails": ["lint not passing"], "sig": "rtl:lint", "detail": ""}
    gr.node_work({**base, "visits": {}, "fails": []})
    gr.node_work({**base, "visits": {"2": 1}})
    assert fired == []                                                           # one failed visit so far
    gr.node_work({**base, "visits": {"2": 2}})
    assert fired == [2]                                                          # two failed visits: the third starts the round
    gr.node_work({**base, "visits": {"2": 3}})
    assert fired == [2]                                                          # one round per stage per run
    rt2 = mk(runs, kway=0)
    gr._RT[rt2.run_id] = rt2
    gr.node_work({**base, "run_id": rt2.run_id, "visits": {"2": 2}})
    gr.node_work({**base, "run_id": rt2.run_id, "visits": {"2": 3}})
    assert fired == [2]                                                          # off by default


# ---- brief 246 (the 214 follow-up): the streak is keyed on the failing gate names, not on the text ------------------------------------------------

def test_signature_from_gate_names_survives_changed_text_and_numbers() -> None:
    a = rg.failure_signature(["lint not passing", "standards STD-RST-01: rtl/a.sv:12: x"], None, ["standards_rtl:STD-RST-01", "lint"])
    b = rg.failure_signature(["standards STD-RST-01: rtl/b.sv:99: other words", "lint not passing"], None, ["lint", "standards_rtl:STD-RST-01"])
    assert a == b == "gates:lint|standards_rtl:STD-RST-01"
    assert rg.failure_signature(["x"], None, ["simulate"]) != a
    assert rg.failure_signature(["x"], "rtl:lint", ["simulate"]) == "rtl:lint"            # stage 2's own signature still wins
    assert rg.failure_signature(["lint failed at line 12"], None, None) == rg.failure_signature(["lint failed at line 99"])    # no gate names: the text form as before


def test_a_bounced_stage_one_loop_reaches_a_streak_of_two_on_the_same_failing_gates() -> None:
    """214's finding: on a stage-1 loop the text signature differed on every entry (streak 1 on visits 2, 3, 4) and escalation never fired. With gate names it does."""
    from agent.graph.stages import MACHINE, exit_check, failed_gates
    st = MACHINE[1]
    ev = {"spec": {}, "lint": {"ok": False}, "simulate": {"ok": False}}
    names = failed_gates(st, ev)
    f = rg.FailureStreak()
    f.see(1, "")
    for text in ("lint not passing at line 3", "lint not passing at line 40 (a different port)", "lint not passing: new words"):
        f.see(1, rg.failure_signature([text], None, names))
    assert names and f.streak(1) == 3
    assert f.see(1, rg.failure_signature(["x"], None, ["simulate"])) == 1                   # a different failing gate: the streak restarts


def test_failed_gates_lists_only_the_gates_that_fail_and_the_standards_rule_ids() -> None:
    from agent.graph.stages import MACHINE, failed_gates
    st = next(s for s in MACHINE if "lint" in s.gates and "simulate" in s.gates)
    ev = {"lint": {"ok": True}, "simulate": {"ok": False}}
    got = failed_gates(st, ev)
    assert "simulate" in got and "lint" not in got
    std = next((s for s in MACHINE if "standards_rtl" in s.gates), None)
    if std is not None:
        res = {"rules": [{"id": "STD-COMB-01", "stage": "rtl", "status": "fail", "findings": [{"file": "a.sv", "line": 3, "message": "m"}]}]}
        assert "standards_rtl:STD-COMB-01" in failed_gates(std, {"standards": res})
