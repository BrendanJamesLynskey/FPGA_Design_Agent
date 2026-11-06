"""Course tier: tasks whose subject is the USB-UART itself (bench.yaml ``no_shell: true``) are compiled without the test shell.

The v1 scoring tool always adds shell/rtl to the sources; a design that has its own ``uart_rx`` / ``uart_tx`` would then clash with the
shell's modules of the same names. v1 stays frozen: this module patches ``benchmark.tools.run_task.sources`` at run time, for the course
tier only, and leaves every other task alone.
"""

from __future__ import annotations

from pathlib import Path

from benchmark.tools import run_task

_orig = run_task.sources


def sources(task: Path, rtl: Path) -> list[Path]:
    b = run_task.load_bench(task)
    if not b.get("no_shell"):
        return _orig(task, rtl)
    src = sorted(p for p in rtl.iterdir() if p.suffix in (".sv", ".v"))
    for stub in b.get("sim_stubs", []):
        src.append(run_task.SIM_STUBS / stub)
    if b.get("wrapper"):
        src.append(task / "hidden" / b["wrapper"])
    return src


def apply() -> None:
    run_task.sources = sources
