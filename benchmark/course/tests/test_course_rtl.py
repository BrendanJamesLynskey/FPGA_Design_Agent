"""Course tier development tasks: the reference RTL passes its hidden acceptance bench (SIM picks the simulator).
Mutants: benchmark/course/tools/check_task.py (CI runs it per task)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from benchmark.course.tools import no_shell
from benchmark.tools import run_task

COURSE = Path(__file__).resolve().parents[1]
TASKS = sorted(d for d in (COURSE / "tasks").iterdir() if d.is_dir())


@pytest.mark.parametrize("task", TASKS, ids=lambda d: d.name)
def test_reference_passes(task: Path) -> None:
    no_shell.apply()
    r = run_task.run(task, sim=os.environ.get("SIM", "icarus"))
    assert r["built"], r.get("error")
    assert r["pass"], {t: ok for t, ok in r["tests"].items() if not ok}
