"""Brief 97: the latency tools through the registry, and the latency loop's keep rule and visit mechanics with a scripted model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.core import registry
from agent.core import tools as _t  # noqa: F401
from agent.core.session import ROOT, Session
from agent.graph import latency_loop as ll
from agent.graph.llm import Reply

DESIGN = ROOT / "designs" / "b96_kr260_10g"


def session() -> Session:
    return Session(design=DESIGN, board="kr260")


def test_latency_path_tool_reconciles_with_the_recorded_bench() -> None:
    r = registry.dispatch(session(), "latency_path", {})
    assert r["ok"] and r["latency_path"]["reconciled"] and r["latency_path"]["total_clocks"] == 13
    assert "rx_ratematch" in r["output"] and "recorded clocks" in r["output"]


def test_latency_budget_tool_names_risk_and_the_board_share() -> None:
    r = registry.dispatch(session(), "latency_budget", {})
    assert r["ok"] and "risk:" in r["output"] and "needs board" in r["output"] and "unattributed" in r["output"]


def test_a_design_without_a_stage_file_is_refused_with_the_reason(tmp_path: Path) -> None:
    d = tmp_path / "designs" / "x"
    d.mkdir(parents=True)
    s = Session(design=d, root=tmp_path)
    r = registry.dispatch(s, "latency_path", {})
    assert not r["ok"] and "has not declared its latency chain" in r["output"]


def test_tool_arguments_are_validated() -> None:
    r = registry.dispatch(session(), "latency_path", {"path": "rm -rf"})
    assert not r["ok"]


def test_keep_rule_is_the_flows() -> None:
    base = {"tests_pass": True, "ttt_clocks": 11, "echo_clocks": 12}
    assert ll.judge(base, {**base, "ttt_clocks": 9})[0]
    assert not ll.judge(base, {**base, "ttt_clocks": 11})[0]
    assert not ll.judge(base, {**base, "ttt_clocks": 9, "tests_pass": False})[0]
    assert not ll.judge(base, {**base, "ttt_clocks": 9, "echo_clocks": 13})[0]


def test_arms_differ_only_in_latency_tools_and_prompt() -> None:
    a1 = [t["function"]["name"] for t in ll.tool_specs("A1")]
    a0 = [t["function"]["name"] for t in ll.tool_specs("A0")]
    assert set(a1) - set(a0) == {"latency_path", "latency_budget"} and set(a0) <= set(a1) and "edit_file" in a0


class Scripted:
    """A model that makes the scripted tool calls one per turn, then stops."""

    def __init__(self, calls):
        self.calls, self.i = calls, 0

    def __call__(self, messages, tools=None):
        if self.i >= len(self.calls):
            return Reply(text="NOTE: scripted change", tool_calls=[], cost=0.001)
        name, args = self.calls[self.i]
        self.i += 1
        return Reply(text="", tool_calls=[{"id": f"c{self.i}", "name": name, "args": args}], cost=0.001)


def visit(arm, calls, tmp_path):
    v = ll.Visit(arm, Scripted(calls), session(), ROOT, DESIGN, max_turns=6)
    return v


def test_the_visit_refuses_writes_outside_rtl_and_the_tools_own_data() -> None:
    v = visit("A0", [], None)
    assert "only rtl/*.sv" in v._dispatch("write_file", {"path": "tests/core_cocotb.py", "content": "x"}, {})
    assert "only rtl/*.sv" in v._dispatch("write_file", {"path": "rtl/sub/x.sv", "content": "x"}, {})
    assert "tools' own data" in v._dispatch("read_file", {"path": "latency_stages.yaml"}, {})
    assert "no such tool" in v._dispatch("latency_path", {}, {})            # arm A0 has no latency tools


def test_edit_file_replaces_exactly_one_occurrence(tmp_path: Path) -> None:
    d = tmp_path / "designs" / "x"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / "a.sv").write_text("module a; // one\n // two\n // one\nendmodule\n")
    v = ll.Visit("A0", Scripted([]), session(), tmp_path, d)
    assert "occurs 2 times" in v._dispatch("edit_file", {"path": "rtl/a.sv", "old": "// one", "new": "x"}, {})
    assert v._dispatch("edit_file", {"path": "rtl/a.sv", "old": "// two", "new": "// 2"}, {}) == "edited rtl/a.sv"
    assert (d / "rtl" / "a.sv").read_text() == "module a; // one\n // 2\n // one\nendmodule\n"
    assert "refused" in v._dispatch("edit_file", {"path": "tests/x.py", "old": "a", "new": "b"}, {})


def test_the_a1_visit_can_call_the_latency_tools() -> None:
    v = visit("A1", [], None)
    out = v._dispatch("latency_path", {}, {})
    assert "tick-to-trade" in out and "rx_ratematch" in out


def test_a_visit_ends_with_the_note(tmp_path: Path) -> None:
    v = visit("A1", [("latency_path", {})], tmp_path)
    r = v.run("sys", "user", {"ttt_clocks": 11, "echo_clocks": 12})
    assert r["ended"] == "done" and r["note"] == "scripted change" and v.tool_counts == {"latency_path": 1}


def test_kb_text_refuses_a_missing_private_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ll, "KB_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        ll.kb_text("latency/loop_system_a1.md")
