"""pytest entry: the unit bench of build rm_gp_itch under cocotb + Icarus (brief 127)."""
from __future__ import annotations

import os
from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
B96 = DESIGN.parent
B110 = B96.parent / "b110_itch_ouch"
ROOT = B96.parents[1]
FILES = [B96 / "rtl/b96_pkg.sv", B110 / "rtl/itch_pkg.sv", DESIGN / "rtl/itch_pkg2.sv", B96 / "rtl/mac64_rx.sv", B96 / "rtl/mac64_tx.sv",
         B110 / "rtl/mold_rx.sv", B110 / "rtl/itch_dec.sv", B110 / "rtl/book_core.sv", B110 / "rtl/risk_glue.sv", B110 / "rtl/ouch_enter.sv",
         DESIGN / "rtl/udp_strip.sv", DESIGN / "rtl/order_seg.sv", DESIGN / "rtl/itch_top.sv", DESIGN / "rtl/itch_path.sv", DESIGN / "rtl/tx_mux.sv", DESIGN / "sim/itch_unit.sv"]


def run(name: str, testcase=None, params=None, extra=None) -> None:
    env = {"PYTHONPATH": str(ROOT)}
    if os.environ.get("B127_RECORD"):
        env["B127_RECORD"] = os.environ["B127_RECORD"]
    env |= extra or {}
    from flow import cocotb_run
    cocotb_run.run(name, "itch_unit", FILES, "b127_unit_cocotb", HERE, parameters=params, testcase=testcase, extra_env=env)


def test_unit_bench() -> None:
    run("b127_unit")
