"""pytest entry: the TCP fast path under cocotb + Icarus against the Python reference (brief 119).

B119_RTL_DIR (a directory with the same file names) swaps in a mutated copy of the RTL: tests/run_mutants.py does that.
B119_RECORD=<absolute dir> writes the measured latencies there."""
from __future__ import annotations

import os
from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]
RTL = Path(os.environ.get("B119_RTL_DIR") or DESIGN / "rtl")
B110_RTL = ROOT / "designs" / "b110_itch_ouch" / "rtl"
FILES = [B110_RTL / "ouch_enter.sv", RTL / "tcp_fast.sv"]


def run(name: str, testcase=None, params=None, extra=None) -> None:
    env = {"PYTHONPATH": str(ROOT)}
    if os.environ.get("B119_RECORD"):
        env["B119_RECORD"] = os.environ["B119_RECORD"]
    env |= extra or {}
    cocotb_run.run(name, "tcp_fast", FILES, "b119_cocotb", HERE, parameters=params, testcase=testcase, extra_env=env)


def test_all_benches() -> None:
    """Every cocotb test of the bench in one simulation."""
    run("b119_all")


def test_behind_the_risk_logic() -> None:
    """Brief 110's path with tcp_fast in place of its stub port (rtl/itch_ouch_tcp_top.sv), against brief 110's reference model."""
    srcs = [B110_RTL / f for f in ("itch_pkg.sv", "mold_rx.sv", "itch_dec.sv", "book_core.sv", "ouch_enter.sv", "risk_glue.sv")] + [RTL / "tcp_fast.sv", RTL / "itch_ouch_tcp_top.sv"]
    env = {"PYTHONPATH": str(ROOT)}
    if os.environ.get("B119_RECORD"):
        env["B119_RECORD"] = os.environ["B119_RECORD"]
    cocotb_run.run("b119_top", "itch_ouch_tcp_top", srcs, "b119_top_cocotb", HERE, extra_env=env)
