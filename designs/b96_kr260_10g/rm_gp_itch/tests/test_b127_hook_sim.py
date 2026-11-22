"""pytest entry: the tcp_fast hook in simulation (Icarus, brief 127). Skipped unless brief 119's tcp_fast.sv is there (B119_RTL, or designs/b119_tcp_fast/rtl/tcp_fast.sv once PR #245 is merged)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

DESIGN = Path(__file__).parent.parent
B96 = DESIGN.parent
B110 = B96.parent / "b110_itch_ouch"
ROOT = B96.parents[1]
TF = Path(os.environ.get("B119_RTL") or ROOT / "designs/b119_tcp_fast/rtl/tcp_fast.sv")
pytestmark = pytest.mark.skipif(not (TF.exists() and shutil.which("iverilog")), reason="needs brief 119's tcp_fast.sv (B119_RTL) and Icarus")


def test_tcp_fast_hook() -> None:
    from flow import cocotb_run
    files = [B96 / "rtl/b96_pkg.sv", B110 / "rtl/itch_pkg.sv", DESIGN / "rtl/itch_pkg2.sv", B96 / "rtl/mac64_rx.sv", B96 / "rtl/mac64_tx.sv",
             *[B110 / f"rtl/{n}.sv" for n in ("mold_rx", "itch_dec", "book_core", "risk_glue", "ouch_enter")], TF,
             DESIGN / "rtl/udp_strip.sv", DESIGN / "rtl/order_seg_tcpfast.sv", DESIGN / "rtl/itch_top.sv", DESIGN / "rtl/itch_path.sv", DESIGN / "rtl/tx_mux.sv", DESIGN / "sim/itch_unit.sv"]
    env = {"PYTHONPATH": str(ROOT)}
    if os.environ.get("B127_RECORD"):
        env["B127_RECORD"] = os.environ["B127_RECORD"]
    cocotb_run.run("b127_hook", "itch_unit", files, "b127_hook_cocotb", Path(__file__).parent, extra_env=env)
