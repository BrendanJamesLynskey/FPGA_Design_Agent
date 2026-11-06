"""Course tier: tasks whose subject is the USB-UART itself (bench.yaml ``no_shell: true``) are compiled without the test shell.

The v1 scoring tool always adds shell/rtl to the sources; a design that has its own ``uart_rx`` / ``uart_tx`` would then clash with the
shell's modules of the same names. v1 stays frozen: this module patches ``benchmark.tools.run_task.sources`` at run time, for the course
tier only, and leaves every other task alone.
"""

from __future__ import annotations

from pathlib import Path

from benchmark.tools import run_task
from flow import srcorder

_orig = run_task.sources
_orig_run = run_task.run


def sources(task: Path, rtl: Path) -> list[Path]:
    b = run_task.load_bench(task)
    if not b.get("no_shell"):
        return srcorder.order_sv(_orig(task, rtl))                  # 07a2-prep: packages and interfaces first, not name order
    src = sorted(p for p in rtl.iterdir() if p.suffix in (".sv", ".v"))
    for stub in b.get("sim_stubs", []):
        src.append(run_task.SIM_STUBS / stub)
    if b.get("wrapper"):
        src.append(task / "hidden" / b["wrapper"])
    return srcorder.order_sv(src)


def run(task: Path, rtl: Path | None = None, sim: str | None = None, seed: int = 1, tag: str = "ref",
        testcase: list[str] | None = None, build_root: Path | None = None) -> dict:
    """``run_task.run`` plus (07a2-prep) the task's ``data/`` files linked into ``hidden/``, the simulator's working
    directory, for the length of the run: ``$readmemh("x.hex")`` and ``$readmemh("data/x.hex")`` find them as they did in the
    agent's own simulation. Only links that did not exist are made and removed (a task whose hidden/ holds its own copy keeps it)."""
    task = task.resolve()
    with srcorder.linked_data(task / "data", task / "hidden"):
        return _orig_run(task, rtl, sim, seed, tag, testcase, build_root)


def apply() -> None:
    run_task.sources = sources
    run_task.run = run
