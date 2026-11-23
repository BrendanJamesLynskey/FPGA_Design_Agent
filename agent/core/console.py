"""The live console's files (brief 182): where each step's output goes while it runs, and the trace rows that point at them.

A step is one model call (the Claude Code stream) or one external tool run (Vivado, the simulator, the formal tool, a test run). Its output is written to
``<run_dir>/console/<step>.log`` while it runs, and the run's own ``trace.jsonl`` gets a ``console`` event naming it (label, stream, source, start) and, when it
ends, a ``console_end`` event (seconds, exit code). The navigator reads the files; it is given step ids, never paths. A prompt is never written here: the Claude
Code stream holds the model's output and tool calls, not the prompt text.

``install`` wraps a runner's ``run`` (on the instance, so ``isinstance`` checks still hold) so every tool run leaves a console file: the local runner streams
into it as the tool runs, the container runner (a docker call) and the replay runners write it when the call ends.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any

from agent.core.trace import Trace

DIR = "console"
STEP = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
_seq: dict[str, int] = {}
_lock = threading.Lock()


def _trace(run_dir: Path) -> Trace:
    return Trace(Path(run_dir) / "trace.jsonl", harness="graph")


def begin(run_dir: Path, label: str, step: str, kind: str = "tool_output", stage: str | None = None) -> Path:
    """Announce a step in the trace and return the file its output goes to (the directory is made)."""
    d = Path(run_dir) / DIR
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{step}.log"
    _trace(run_dir).event("console", stage, step=step, label=label[:60], stream=kind, source=f"{DIR}/{step}.log", started=round(time.time(), 1))
    return f


def end(run_dir: Path, step: str, seconds: float, rc: int | None = None) -> None:
    _trace(run_dir).event("console_end", None, step=step, seconds=round(float(seconds), 1), returncode=rc)


def next_step(run_dir: Path, kind: str) -> str:
    """``<n>_<kind>``: n continues over the files already in console/ (a resumed run does not reuse a number)."""
    key = str(run_dir)
    d = Path(run_dir) / DIR
    with _lock:
        have = max((int(m.group(1)) for p in d.glob("*.log") if (m := re.match(r"(\d+)_", p.name))), default=0) if d.is_dir() else 0
        n = max(_seq.get(key, 0), have) + 1
        _seq[key] = n
    return f"{n:03d}_{re.sub(r'[^A-Za-z0-9_.-]', '-', kind)[:40]}"


def install(runner: Any, run_dir: Path, stage_of: Any = None) -> Any:
    """Wrap ``runner.run`` so each tool run writes console/<step>.log. Safe to call twice (the second call does nothing)."""
    if getattr(runner, "_console_installed", None) == str(run_dir):
        return runner
    inner = runner.run

    def run(kind, argv, cwd, env=None, timeout=600):
        step = next_step(run_dir, kind)
        f = begin(run_dir, kind, step, "tool_output", stage_of() if callable(stage_of) else None)
        try:
            runner._tee_to = f
        except Exception:                                  # a runner that refuses attributes just writes at the end
            pass
        t0 = time.time()
        try:
            res = inner(kind, argv, cwd, env, timeout)
        finally:
            try:
                runner._tee_to = None
            except Exception:
                pass
        try:
            if not f.is_file() or f.stat().st_size == 0:      # a runner that did not stream: the output as it ended
                out = str(getattr(res, "stdout", "") or "")
                err = str(getattr(res, "stderr", "") or "")
                f.write_text(out + (("\n--- stderr ---\n" + err) if err else ""))
            end(run_dir, step, time.time() - t0, getattr(res, "returncode", None))
        except Exception:                                  # the console is a view: never fail a tool run because of it
            pass
        return res
    try:
        runner.run = run
        runner._console_installed = str(run_dir)
    except Exception:
        pass
    return runner
