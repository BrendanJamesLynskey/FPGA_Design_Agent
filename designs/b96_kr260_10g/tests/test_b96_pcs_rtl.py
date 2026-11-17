"""pytest entry: the PCS and MAC under cocotb + Icarus against the Python reference (brief 96)."""

from __future__ import annotations

from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]
RTL = DESIGN / "rtl"


def test_pcs_mac_cocotb() -> None:
    srcs = [RTL / "b96_pkg.sv", RTL / "pcs_tx.sv", RTL / "pcs_rx.sv", RTL / "mac64_tx.sv", RTL / "mac64_rx.sv", DESIGN / "sim" / "tb_pcs_mac.sv"]
    cocotb_run.run("b96_pcs_mac", "tb_pcs_mac", srcs, "pcs_mac_cocotb", HERE, extra_env={"PYTHONPATH": str(ROOT)})
