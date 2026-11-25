"""pytest entry: the PS-AXI latency probe under cocotb + Icarus (brief 191). B191_RECORD=<absolute dir> writes the simulated interval record there; B191_RTL_DIR swaps in a mutated copy of the RTL (tests/run_mutants.py)."""
from __future__ import annotations

import os
from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]
RTL = Path(os.environ.get("B191_RTL_DIR") or DESIGN / "rtl")


def test_probe_benches() -> None:
    """Every cocotb test of the bench in one simulation."""
    env = {"PYTHONPATH": str(ROOT)}
    if os.environ.get("B191_RECORD"):
        env["B191_RECORD"] = os.environ["B191_RECORD"]
    cocotb_run.run("b191_probe", "axi_lat_probe", [RTL / "axi_lat_probe.sv"], "b191_cocotb", HERE, extra_env=env)
