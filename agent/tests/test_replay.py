"""Replayed-trace CI: a recorded T1 episode (clarify -> ... -> bitstream) run through the real core, no model spend.

`agent/tests/fixtures/t1_episode.json` was recorded on real tools by `python -m agent.core.smoke --record`
(lint, Icarus simulation, formal, Vivado to the bitstream). Here the tools' side is replayed, so the core's schemas,
jail, allow-lists, argv construction, audit and trace are exercised exactly as in a live run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.core import dispatch
from agent.core.replay import replay
from agent.core.runner import RecordedRunner
from agent.core.session import STAGES, Session
from agent.core.trace import Trace, read_trace
from agent.tests.conftest import StubBank

EPISODE = json.loads((Path(__file__).parent / "fixtures" / "t1_episode.json").read_text())


def test_episode_replays_through_the_core(tmp_path: Path) -> None:
    out = replay(EPISODE, tmp_path / "w", bank=StubBank(), trace_path=tmp_path / "trace.jsonl")
    s, results = out["session"], out["results"]
    assert len(results) == len(EPISODE["steps"]) and all(r["ok"] or not r["refused"] for r in results)
    assert not s.audit.refusals()
    assert s.stage == "power-closure"
    gates = [r for r in results if r["tool"] == "gates"][-1]
    assert gates["gates"]["pass"] is True and gates["gates"]["first_failed_stage"] is None
    assert all(gates["gates"]["stages"][st]["pass"] for st in ("rtl", "post_synth", "post_place", "post_route", "bitstream"))
    audit = [json.loads(l) for l in (s.design / "build" / "audit.jsonl").read_text().splitlines()]
    assert len(audit) == len(EPISODE["steps"]) and {a["stage"] for a in audit} <= set(STAGES)


def test_trace_format(tmp_path: Path) -> None:
    replay(EPISODE, tmp_path / "w", bank=StubBank(), trace_path=tmp_path / "trace.jsonl")
    tr = read_trace(tmp_path / "trace.jsonl")
    models = [r for r in tr if r["kind"] == "model"]
    tools = [r for r in tr if r["kind"] == "tool"]
    assert len(models) == len(tools) == len(EPISODE["steps"])
    assert all(r["v"] == 1 and r["fake"] is True and r["cost_usd"] == 0.0 for r in models)   # a fake reports no real cost
    assert {"harness", "model", "tokens", "cost_usd", "stage", "seconds"} <= set(models[0])
    assert {"tool", "arguments", "result", "stage", "seconds"} <= set(tools[0])
    assert [r["seq"] for r in tr] == list(range(1, len(tr) + 1))


def test_trace_refuses_an_invented_cost(tmp_path: Path) -> None:
    t = Trace(None)
    t.model("m", None, "unreported", "clarify")
    with pytest.raises(ValueError):
        t.model("m", None, "about 3 cents", "clarify")


def test_replay_fails_if_the_core_changes_a_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agent.core.tools as tools
    monkeypatch.setattr(tools, "STOPS", tools.STOPS)
    bad = json.loads(json.dumps(EPISODE))
    next(r for r in bad["runs"] if r["kind"] == "lint")["argv"][1] = "--lint-everything"
    with pytest.raises(AssertionError, match="argv changed"):
        replay(bad, tmp_path / "w", bank=StubBank())


def test_replay_fails_if_the_episode_drifts(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(EPISODE))
    bad["steps"][1]["expect"]["digest"] = "0" * 16
    with pytest.raises(AssertionError, match="output changed"):
        replay(bad, tmp_path / "w", bank=StubBank())
