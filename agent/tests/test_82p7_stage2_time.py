"""Brief 82P7: the Icarus cross-check runs once (after the other stage-2 gates pass), a simulation time-out says where it was,
the first fully clean evaluation is a clean stop, a killed run has a summary.json, CONST-ID-01 persistence counts any earlier visit,
and stop-reason assertions carry no traceback or absolute path. No model call."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from agent.core import dispatch
from agent.core import tools as tl
from agent.core.runner import RunResult
from agent.core.session import ROOT
from agent.graph import killed, repair
from agent.graph import run as gr
from agent.tests.conftest import FakeRunner
from agent.tests.test_07a2_fix5_e import SimRunner, _both

T1 = ROOT / "designs" / "t1_dimmer_counter"


class OkRunner:
    def run(self, kind, argv, cwd, env=None, timeout=600):
        return RunResult(0, f"{kind}: ok", "", 0.0)


@pytest.fixture
def rt(monkeypatch):
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="off", verif_level="V2")
    r = gr.new_runtime(cfg, lambda *a, **k: None, runner=OkRunner())
    from flow import architecture as _am
    _am.write_approval(r.design, "auto", "agent")
    yield r
    shutil.rmtree(runs, ignore_errors=True)


# ---- the cross-check runs once, last ---------------------------------------------------------------------------------------------
def _stub_gate(monkeypatch, rt, sim_results, verif_reached="V2", spec_blocks=False):
    """node_gate(stage 2) with every tool stubbed; returns the list of (tool, sim) calls."""
    calls: list = []

    def fake_dispatch(session, tool, args):
        calls.append((tool, (args or {}).get("sim") or (args or {}).get("kind")))
        if tool == "simulate":
            return dict(sim_results[(args or {}).get("sim", "auto")])
        if tool == "gates":
            return {"gates": ({"reached": verif_reached, "stages": {}} if args.get("kind") == "verif" else {"rules": []})}
        return {"ok": True, "output": ""}

    monkeypatch.setattr(gr, "dispatch", fake_dispatch)
    monkeypatch.setattr(gr, "_contract", lambda rt_, detail: {"ok": True})
    monkeypatch.setattr(gr, "trace_record", lambda *a, **k: {})
    monkeypatch.setattr(gr, "constants_gate", lambda rt_: {"findings": []})
    monkeypatch.setattr(gr, "_build", lambda rt_, until, variant="base": calls.append(("build", until)) or {"build": {}, "gates": {"stages": {"rtl": {"ran": True, "gates": {"rtl_clean": True}}}}})
    monkeypatch.setattr(gr, "spec_test_gate", lambda rt_: {"blocks": spec_blocks, "evidence": "spec bench fails"})
    return calls


PASS = {"ok": True, "sim": "verilator", "output": "1 passed"}
ICARUS_OK = {"ok": True, "sim": "icarus", "output": "1 passed"}
FAIL = {"ok": False, "sim": "verilator", "output": "x", "log_tail": "x",
        "first_failure": {"test": "t", "message": ["AssertionError: a != b"], "where": None, "cause": [], "frames": [], "log_errors": []}}


def test_icarus_runs_once_after_the_other_gates_pass(rt, monkeypatch):
    calls = _stub_gate(monkeypatch, rt, {"auto": PASS, "icarus": ICARUS_OK})
    out = gr.node_gate({"run_id": rt.run_id, "stage": 2})
    sims = [c for c in calls if c[0] == "simulate"]
    assert sims == [("simulate", "auto"), ("simulate", "icarus")]                    # Verilator first, Icarus once
    assert calls.index(("simulate", "icarus")) > calls.index(("gates", "verif")) > calls.index(("simulate", "auto"))
    assert out["evidence"]["simulate"]["sim"] == "verilator+icarus" and out["evidence"]["cross_check"]["ran"] is True


def test_no_icarus_run_while_another_gate_fails(rt, monkeypatch):
    calls = _stub_gate(monkeypatch, rt, {"auto": PASS, "icarus": ICARUS_OK}, verif_reached="V1")        # V2 not reached
    out = gr.node_gate({"run_id": rt.run_id, "stage": 2})
    assert [c for c in calls if c[0] == "simulate"] == [("simulate", "auto")]
    assert out["evidence"]["cross_check"] == {"ran": False} and out["fails"]
    calls = _stub_gate(monkeypatch, rt, {"auto": PASS, "icarus": ICARUS_OK}, spec_blocks=True)
    rt.cfg.spec_tests = True
    out = gr.node_gate({"run_id": rt.run_id, "stage": 2})
    assert ("simulate", "icarus") not in calls and out["fails"]


def test_no_icarus_run_when_the_verilator_run_fails(rt, monkeypatch):
    calls = _stub_gate(monkeypatch, rt, {"auto": FAIL, "icarus": ICARUS_OK})
    out = gr.node_gate({"run_id": rt.run_id, "stage": 2})
    assert ("simulate", "icarus") not in calls and not out["evidence"]["simulate"]["ok"] and set(out["owners"]) >= {"rtl"}


def test_a_failing_cross_check_is_a_simulation_failure_for_the_repair(rt, monkeypatch):
    icarus_fail = {**FAIL, "sim": "icarus", "first_failure": {**FAIL["first_failure"], "message": ["AssertionError: icarus only"]}}
    _stub_gate(monkeypatch, rt, {"auto": PASS, "icarus": icarus_fail})
    out = gr.node_gate({"run_id": rt.run_id, "stage": 2})
    assert out["evidence"]["simulate"]["sim"] == "icarus (cross-check)" and not out["evidence"]["simulate"]["ok"]
    assert out["fails"] and "rtl" in out["owners"] and "icarus only" in out["owners"]["rtl"][0]


def test_an_icarus_only_design_is_not_cross_checked_again(rt, monkeypatch):
    calls = _stub_gate(monkeypatch, rt, {"auto": ICARUS_OK, "icarus": ICARUS_OK})
    gr.node_gate({"run_id": rt.run_id, "stage": 2})
    assert [c for c in calls if c[0] == "simulate"] == [("simulate", "auto")]


def test_simulate_gate_default_still_cross_checks_at_once(session, monkeypatch):
    _both(monkeypatch)
    session.runner = SimRunner({"verilator": RunResult(0, "ok", "", 4.0), "icarus": RunResult(0, "ok", "", 40.0)})
    assert gr.simulate_gate(session)["sim"] == "verilator+icarus" and session.runner.sims == ["verilator", "icarus"]
    session.runner = SimRunner({"verilator": RunResult(0, "ok", "", 4.0), "icarus": RunResult(0, "ok", "", 40.0)})
    g = gr.simulate_gate(session, cross_check=False)
    assert g["sim"] == "verilator" and session.runner.sims == ["verilator"]


# ---- the clean stop --------------------------------------------------------------------------------------------------------------
def test_the_first_fully_clean_evaluation_is_a_clean_stop(rt, monkeypatch):
    _stub_gate(monkeypatch, rt, {"auto": PASS, "icarus": ICARUS_OK})
    rt.cfg.stop_after = 2
    gr._RT[rt.run_id] = rt
    st = gr.node_gate({"run_id": rt.run_id, "stage": 2})
    assert st["fails"] == [] and st["owners"] == {} and st["repeat"] == 0
    state = {"run_id": rt.run_id, "stage": 2, "fails": st["fails"], "history": [{"n": 2, "stage": "rtl-design-creation", "passed": True, "approval": {"decision": "approve", "by": "auto"}}],
             "evidence": st["evidence"]}
    adv = gr.node_advance(state)
    assert adv == {"stop": "done"}                                                    # no further visit, no loop back
    assert gr.route({**state, **adv}) == "end"
    assert gr.summary(rt, {**state, **adv})["clean_stop"] is True


def test_no_graph_edge_keeps_a_clean_run_iterating():
    import inspect
    src = inspect.getsource(gr.node_advance)
    assert "loopback" in src                                                          # the only loop-back besides failures and rewinds
    st = {"run_id": "x", "stage": 2, "fails": [], "history": [{"n": 2}], "loopback": {}}
    rt = SimpleNamespace(cfg=SimpleNamespace(stop_after=2, spec_tests=False), design=Path("/nonexistent"))
    gr._RT["x"] = rt
    try:
        assert gr.node_advance(st) == {"stop": "done"}
        assert gr.node_advance({**st, "stage": 3, "fails": []}) == {"stop": "done"}      # a later stage than stop_after: also stops
        assert gr.node_advance({**st, "fails": ["simulate not passing"]})["stage"] == 2    # a failure still repairs
    finally:
        gr._RT.pop("x")


# ---- time-out diagnosis ---------------------------------------------------------------------------------------------------------------
def test_a_simulation_timeout_is_diagnosed_from_the_log_tail(session, monkeypatch):
    _both(monkeypatch)
    log = session.root / "build" / "sim" / "x"
    log.mkdir(parents=True)
    (log / "sim.log").write_text("".join(f"{i * 1000:>10.2f}ns INFO     cocotb.test  step {i}\n" for i in range(1, 40)))
    tl.record_sim_baseline(session.design, "verilator", 540)
    session.runner = SimRunner({"icarus": RunResult(124, "", "timed out after 1800 s", 1800.7)})
    r = dispatch(session, "simulate", {"sim": "icarus"})
    ff = r["first_failure"]
    assert not r["ok"] and r["kind"] == "sim_timeout" and ff["timeout"] is True
    assert "within" in ff["message"][0] and "39000.00 ns" in ff["message"][0] and "540 s on Verilator" in ff["message"][0]
    assert ff["cause"] and "step 39" in ff["cause"][-1] and "simulation timed out" in r["output"]
    role, kind = repair.classify_sim(ff, r["output"])
    assert (role, kind) == ("rtl", "timeout")


def test_a_timeout_does_not_ask_the_bench_owner_to_check_the_bench():
    ff = {"test": "icarus run (timed out)", "message": ["icarus did not finish within 1800 s of wall time"], "timeout": True, "cause": [],
          "frames": [], "log_errors": [], "where": None}
    ev = {"lint": {"ok": True}, "standards_fails": [], "constants": None, "contract": {"ok": True},
          "simulate": {"ok": False, "first_failure": ff, "text": "t"}, "verif": {"reached": "V2"}, "verif_level": "V2"}
    o, sig = repair.stage2_owners(ev, repeat=2)
    assert list(o) == ["rtl"] and "sim:icarus run (timed out)" in sig                   # no hint to the Verifier or the Modeller
    why, d = repair.stop_diagnosis(2, 6, {"evidence": ev, "owners": o, "sig": sig, "repeat": 2, "fails": []})
    assert "last failing assertion: icarus run (timed out): icarus did not finish within 1800 s" in why and "Traceback" not in why


def test_the_icarus_limit_comes_from_the_verilator_baseline_until_icarus_has_one(tmp_path):
    d = tmp_path
    assert tl.sim_timeout(d, "icarus") == 1800                                           # nothing measured
    tl.record_sim_baseline(d, "verilator", 540)
    assert tl.sim_timeout(d, "icarus") == 3360                                           # 6 x 540 + 120
    tl.record_sim_baseline(d, "verilator", 60)
    assert tl.sim_timeout(d, "icarus") == 1800                                           # the floor
    tl.record_sim_baseline(d, "verilator", 5000)
    assert tl.sim_timeout(d, "icarus") == 5400                                           # the ceiling
    tl.record_sim_baseline(d, "icarus", 700)
    assert tl.sim_timeout(d, "icarus") == 2920 and tl.sim_timeout(d, "verilator") == 7200   # its own baseline wins


# ---- stop-reason text ----------------------------------------------------------------------------------------------------------------
def test_assertion_text_has_no_traceback_and_no_absolute_path():
    ff = {"test": "test_v2_e_udp_endpoint_rtl",
          "message": ['Traceback (most recent call last):',
                      'File "/home/brendan/Claude_sandbox/_worktrees/82p6-frozen/runs/2026/v2/tests/bench_udp_endpoint.py", line 273, in test_reset_smoke',
                      'assert dut == model',
                      "AssertionError: status 2 expected 0 at /home/brendan/x/y/bench.py"]}
    t = repair.clean_assertion(ff)
    assert t == "AssertionError: status 2 expected 0 at bench.py" and "/home" not in t and "Traceback" not in t
    ff2 = {"message": ['Traceback (most recent call last):\n  File "/a/b/c/bench.py", line 9, in f\n    foo()\nValueError: boom 0x5']}
    assert repair.clean_assertion(ff2) == "ValueError: boom 0x5"
    only_frames = {"message": ['Traceback (most recent call last):', 'File "/a/b/c/bench.py", line 9, in f']}
    assert "/a/b" not in repair.clean_assertion(only_frames)
    assert len(repair.clean_assertion({"message": ["AssertionError: " + "x" * 900]})) <= 200


def test_the_82p6_a_r3_reason_is_trimmed():
    ff = {"test": "test_v2_e_udp_endpoint_rtl",
          "message": ["Traceback (most recent call last): | File \"/home/brendan/Claude_sandbox/_worktrees/82p6-frozen/runs/20261121-064355-1ea8/v2_e_udp_endpoint/tests/bench_udp_endpoint.py\", line 273, in test_reset_smoke",
                      "AssertionError: reset smoke: design ID 0x55445031 != 0x55455031"]}
    why, d = repair.stop_diagnosis(2, 6, {"evidence": {"simulate": {"ok": False, "first_failure": ff}}, "owners": {"rtl": []},
                                         "sig": "rtl:sim:x", "repeat": 4, "fails": []})
    assert "/home" not in why and "Traceback" not in why and "design ID 0x55445031 != 0x55455031" in why
    assert d["last_failing_assertion"].endswith("0x55455031")


# ---- CONST-ID-01 persistence ------------------------------------------------------------------------------------------------------------
def test_const_id_persists_when_it_recurred_at_any_earlier_visit():
    f = {"code": "CONST-ID-01", "blocking": True, "bound": 0x55445031}
    right = {"findings": []}
    # 82P6 A r3: wrong at visits 1, 3, 5, right at 2 and 4. At visit 3 the previous table is clean: the old rule said no.
    seen: list = []
    t1 = gr.mark_persisted(None, {"findings": [f]}, seen)
    assert "persisted" not in t1
    seen = sorted(set(seen) | gr._const_ids(t1))
    t2 = gr.mark_persisted(t1, right, seen)
    assert "persisted" not in t2
    t3 = gr.mark_persisted(t2, {"findings": [f]}, seen)
    assert t3["persisted"] is True and "persisted" not in gr.mark_persisted(t2, {"findings": [f]})   # without the history it would not
    other = {"code": "CONST-ID-01", "blocking": True, "bound": 1}
    assert "persisted" not in gr.mark_persisted(t2, {"findings": [other]}, seen)                 # a different value is new


def test_node_gate_keeps_the_values_seen_at_earlier_visits(rt, monkeypatch):
    f = {"code": "CONST-ID-01", "blocking": True, "bound": 7, "expected": 8, "message": "m", "where": "x", "holders": []}
    tables = iter([{"findings": [f]}, {"findings": []}, {"findings": [f]}])
    _stub_gate(monkeypatch, rt, {"auto": PASS, "icarus": ICARUS_OK})
    monkeypatch.setattr(gr, "constants_gate", lambda rt_: next(tables))
    e1 = gr.node_gate({"run_id": rt.run_id, "stage": 2})["evidence"]
    e2 = gr.node_gate({"run_id": rt.run_id, "stage": 2, "evidence": e1})["evidence"]
    e3 = gr.node_gate({"run_id": rt.run_id, "stage": 2, "evidence": e2})["evidence"]
    assert "persisted" not in e1["constants"] and "persisted" not in e2["constants"] and e3["constants"]["persisted"] is True
    assert e3["const_id_seen"] == [7]


# ---- killed runs ---------------------------------------------------------------------------------------------------------------------
def _fake_run_dir(tmp_path: Path) -> Path:
    rd = tmp_path / "20261121-000000-abcd"
    des = rd / "v2_e_udp_endpoint"
    (des / "build").mkdir(parents=True)
    (rd / "config.json").write_text(json.dumps({"name": "v2_e_udp_endpoint", "spec_tests": True}))
    rows = [{"stage": "clarify", "visit": 1, "role": "clarify", "tokens": 100, "turns": 3, "wall_s": 10.0, "plan_cost_estimate_usd": 0.5},
            {"stage": "rtl-design-creation", "visit": 1, "role": "rtl", "tokens": 900, "turns": 20, "wall_s": 600.0, "ended": "done",
             "plan_cost_estimate_usd": 2.25},
            {"stage": "rtl-design-creation", "visit": 2, "role": "rtl", "tokens": 400, "turns": 9, "wall_s": 90.0, "ended": "done",
             "plan_cost_estimate_usd": 0.75}]
    (rd / "role_usage.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (rd / "claude_code_calls.jsonl").write_text(json.dumps({"claude_code_version": "2.1.321", "plan_cost_estimate_usd": 3.5}) + "\n")
    (rd / "snapshots.json").write_text(json.dumps([{"n": 0}, {"n": 1}, {"n": 2}, {"n": 2}]))
    (rd / "routing_events.jsonl").write_text(json.dumps({"event": "p1_hint_sent"}) + "\n")
    audit = [{"t": 1, "tool": "simulate", "role": None, "arguments": {"sim": "icarus"}, "seconds": 1800.0, "stage": "rtl-design-creation"},
             {"t": 2, "tool": "simulate", "role": None, "arguments": {"sim": "auto"}, "seconds": 500.0, "stage": "rtl-design-creation"}]
    (des / "build" / "audit.jsonl").write_text("\n".join(json.dumps(a) for a in audit) + "\n")
    return rd


def test_a_killed_run_gets_a_summary_with_cost_and_last_state(tmp_path):
    rd = _fake_run_dir(tmp_path)
    p = killed.write_killed_summary(rd, 14400, 14400.6)
    s = json.loads(p.read_text())
    assert s["stop"].startswith("budget:") and s["clean_stop"] is False and s["killed"] is True
    assert s["tokens"] == 1400 and s["turns"] == 32 and s["plan_cost_estimate_usd"] == 3.5 and s["stages_visited"] == [0, 1, 2, 2]
    assert s["stop_detail"]["stage2_visits"] == 2 and s["stop_detail"]["gate_simulation_s"] == {"gate_icarus": 1800.0, "gate_verilator": 500.0}
    assert s["routing_events"] == [{"event": "p1_hint_sent"}] and s["per_role"]["rtl"]["calls"] == 2
    assert s["design"] == "v2_e_udp_endpoint" and s["spec_test"] in ({}, {"fired": False})
    assert killed.write_killed_summary(rd, 14400, 1) is None and json.loads(p.read_text())["wall_s"] == 14400.6     # never overwritten


def test_killed_summary_is_what_the_driver_reads(tmp_path):
    rd = _fake_run_dir(tmp_path)
    s = killed.killed_summary(rd, 14400)
    for k in ("tokens", "plan_cost_estimate_usd", "turns", "stop", "stages_visited", "gates_last", "spec_test", "clean_stop",
              "stop_detail", "per_stage", "routing_events"):
        assert k in s
