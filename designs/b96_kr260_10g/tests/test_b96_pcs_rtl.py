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


def test_core_cocotb() -> None:
    xpm_free = []
    srcs = [RTL / "b96_pkg.sv", RTL / "pcs_tx.sv", RTL / "pcs_rx.sv", RTL / "mac64_tx.sv", RTL / "mac64_rx.sv", RTL / "hs_vec.sv",
            RTL / "frame_src.sv", RTL / "trade64.sv", RTL / "tx_path.sv", RTL / "rx_path.sv", RTL / "b96_core.sv",
            DESIGN / "sim" / "gth_wiz_model96.sv", DESIGN / "sim" / "tb_core.sv"] + xpm_free
    cocotb_run.run("b96_core", "tb_core", srcs, "core_cocotb", HERE, extra_env={"PYTHONPATH": str(ROOT)})
