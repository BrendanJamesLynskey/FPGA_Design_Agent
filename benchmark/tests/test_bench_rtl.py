"""Benchmark v1, development tasks: the reference RTL passes its hidden acceptance bench (CI rtl-sim job; SIM picks
the simulator). Mutants and traps: benchmark/tools/check_task.py (CI runs it per task)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from benchmark.tools import run_task

BENCH = Path(__file__).resolve().parents[1]
TASKS = sorted(d for d in (BENCH / "tasks").iterdir() if d.is_dir())


@pytest.mark.parametrize("task", TASKS, ids=lambda d: d.name)
def test_reference_passes(task: Path) -> None:
    r = run_task.run(task, sim=os.environ.get("SIM", "icarus"))
    assert r["built"], r.get("error")
    assert r["pass"], {t: ok for t, ok in r["tests"].items() if not ok}
