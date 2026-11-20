"""pytest entry: the whole path under cocotb + Icarus against the Python reference (brief 110).

B110_RTL_DIR (a directory with the same file names) swaps in a mutated copy of the RTL: tests/run_mutants.py does that.
B110_RECORD=<absolute dir> writes the measured latencies (latency_sim.json) there."""
from __future__ import annotations

import os
from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]
RTL = Path(os.environ.get("B110_RTL_DIR") or DESIGN / "rtl")
FILES = ["itch_pkg.sv", "mold_rx.sv", "itch_dec.sv", "book_core.sv", "ouch_enter.sv", "risk_glue.sv", "itch_ouch_top.sv"]


def run(name: str, testcase=None, params=None, extra=None) -> None:
    env = {"PYTHONPATH": str(ROOT)}
    if os.environ.get("B110_RECORD"):
        env["B110_RECORD"] = os.environ["B110_RECORD"]
    env |= extra or {}
    cocotb_run.run(name, "itch_ouch_top", [RTL / f for f in FILES], "b110_cocotb", HERE, parameters=params, testcase=testcase, extra_env=env)


def test_main_stream() -> None:
    run("b110_main", testcase="main_stream")
