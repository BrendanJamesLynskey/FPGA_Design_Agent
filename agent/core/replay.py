"""Scripted and replayed episodes: an agent run with no model spend.

An episode file (JSON) holds the *model's side* of a run (``steps``: stage, tool, arguments) and the *tools'
side* as recorded on real tools (``runs``: the argv, output and files of every command the core ran).
:func:`replay` feeds the steps through :func:`agent.core.registry.dispatch` with a
:class:`~agent.core.runner.RecordedRunner`, so CI exercises the real core (schemas, jail, allow-lists, audit,
trace, gates parsing of recorded gate files) without Vivado, a board or an LLM, and fails if the core would now
run a different command than the one recorded.

:class:`ScriptedModel` is the model fake: it emits the steps one at a time and writes model records with
``fake: true`` and ``cost_usd: 0.0`` to the trace (a fake never reports a provider cost).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from agent.core.registry import dispatch
from agent.core.runner import RecordedRunner
from agent.core.session import ROOT, Session
from agent.core.trace import Trace

DETERMINISTIC = ("read_file", "list_files", "check_constraints", "write_file")


def digest(res: dict[str, Any]) -> str:
    return hashlib.sha256(res.get("output", "").encode()).hexdigest()[:16]


class ScriptedModel:
    provider = "fake"
    model = "scripted"

    def __init__(self, steps: list[dict[str, Any]], trace: Trace | None = None):
        self.steps = list(steps)
        self.trace = trace

    def next(self, stage: str) -> dict[str, Any] | None:
        if not self.steps:
            return None
        step = self.steps.pop(0)
        if self.trace is not None:
            self.trace.model("scripted", {"input": 0, "output": 0}, 0.0, stage, fake=True)
        return step


def make_workdir(tmp: Path, design: str) -> Path:
    """A throw-away repo root for a replay: a copy of the design, shell/ and boards/, the real flow/ and tools/."""
    (tmp / "designs").mkdir(parents=True)
    shutil.copytree(ROOT / "designs" / design, tmp / "designs" / design,
                    ignore=shutil.ignore_patterns("build", "__pycache__", "BUILD_NOTE.md"))
    shutil.copytree(ROOT / "shell", tmp / "shell", ignore=shutil.ignore_patterns("tests", "__pycache__", "build"))
    shutil.copytree(ROOT / "boards", tmp / "boards")
    for d in ("flow", "tools"):
        (tmp / d).symlink_to(ROOT / d)
    return tmp / "designs" / design


def replay(episode: dict[str, Any], tmp: Path, bank: Any = None, trace_path: Path | None = None) -> dict[str, Any]:
    design = make_workdir(tmp, episode["design"])
    trace = Trace(trace_path, harness="replay")
    s = Session(design=design, root=tmp, runner=RecordedRunner(episode["runs"]), bank=bank, trace=trace)
    model = ScriptedModel(episode["steps"], trace)
    results = []
    while (step := model.next(s.stage)) is not None:
        res = dispatch(s, step["tool"], step.get("arguments", {}))
        results.append(res)
        want = step.get("expect", {})
        for k in ("ok", "refused"):
            if k in want:
                assert res.get(k) == want[k], f"step {len(results)} {step['tool']}: {k} was {res.get(k)}, recorded {want[k]}: {res['output'][:300]}"
        if "digest" in want:
            assert digest(res) == want["digest"], f"step {len(results)} {step['tool']}: output changed"
    assert s.runner.i == len(s.runner.records), "replay: recorded runs left unused"
    return {"session": s, "results": results}
