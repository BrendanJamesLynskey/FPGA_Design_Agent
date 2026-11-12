"""Brief 50A: the agent's debug tools through dispatch (the MCP server's one entry point)."""

from __future__ import annotations

import json

from agent.core import dispatch
from debug_core import capture as C
from debug_core.instruments import MockIla
from debug_core.plan import make_plan

INTENT = {"probes": ["count"], "trigger": {"combine": "AND", "conditions": [
    {"signal": "win_wr", "op": "==", "value": 1}, {"signal": "addr", "op": "==", "value": "0x80"}]}, "pre": 16, "post": 32}


def test_debug_plan_resolves_and_saves(session) -> None:
    r = dispatch(session, "debug_plan", {"intent": INTENT, "request": "count when the shell writes COUNT"})
    assert r["ok"] and r["buildable"] and len(r["probeset"]) == 12
    assert "win_wr == 1 AND addr == 0x80" in r["output"]
    plan = json.loads((session.design / r["plan_file"]).read_text())
    assert [p["pins"] for p in plan["probes"]][-1] == "u_dut/count_reg[*]/Q"


def test_debug_plan_reports_unknown_names(session) -> None:
    r = dispatch(session, "debug_plan", {"intent": {"probes": ["fifo_overflow"], "trigger": {"combine": "AND", "conditions": [
        {"signal": "uart_byte", "op": "==", "value": 65}]}}})
    assert not r["ok"] and not r["buildable"] and "CANNOT BE BUILT" in r["output"]
    assert {e["what"] for e in r["errors"]} >= {"signal 'fifo_overflow'", "signal 'uart_byte'"}


def test_debug_plan_refuses_a_malformed_intent(session) -> None:
    r = dispatch(session, "debug_plan", {"intent": {"probes": "count"}})
    assert not r["ok"]


def test_debug_capture_needs_the_hardware_stage(session) -> None:
    pid = dispatch(session, "debug_plan", {"intent": INTENT})["probeset"]
    r = dispatch(session, "debug_capture", {"probeset": pid})
    assert r["refused"] and r["rule"] == "hardware-stage"


def test_debug_capture_without_a_build_asks_for_one_and_touches_nothing(session, board_file) -> None:
    pid = dispatch(session, "debug_plan", {"intent": INTENT})["probeset"]
    session.stage = "configuration-and-debug"
    r = dispatch(session, "debug_capture", {"probeset": pid})
    assert not r["ok"] and r["needs_build"] and session.runner.calls == []
    bad = dispatch(session, "debug_capture", {"probeset": "../../etc"})
    assert bad["refused"]


def test_debug_query_reads_a_capture_under_build_debug_only(session) -> None:
    plan = make_plan(session.design, INTENT)
    n, t0 = 1024, 16
    m = MockIla({"win_wr": [int(k == t0) for k in range(n)], "addr": [0x80] * n,
                 "count": [3 if k <= t0 else 0x1234 for k in range(n)]}, t0)
    m.configure(plan)
    f = C.save(m.capture(), session.design / "build" / "debug" / "runs" / "x" / "capture.json")
    rel = str(f.relative_to(session.design))
    r = dispatch(session, "debug_query", {"capture": rel, "query": {"op": "first", "channel": "count", "cmp": "==",
                                                                     "value": "0x1234"}})
    assert r["ok"] and r["cycle"] == 1
    out = dispatch(session, "debug_query", {"capture": "spec.yaml", "query": {"op": "summary"}})
    assert out["refused"]


def test_debug_capture_has_a_hardware_cost() -> None:
    from agent.core.registry import TOOLS
    from agent.core.security import HW_COST, HardwarePolicy
    assert TOOLS["debug_capture"].hardware and HW_COST["debug_capture"] == 1
    hp = HardwarePolicy(2)
    hp.charge("debug_capture")
    hp.charge("debug_capture")
    import pytest
    from agent.core.security import SecurityError
    with pytest.raises(SecurityError):
        hp.charge("debug_capture")
