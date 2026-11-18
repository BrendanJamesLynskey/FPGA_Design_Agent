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
            RTL / "frame_src.sv", RTL / "trade64.sv", RTL / "rate_match.sv", RTL / "tx_path.sv", RTL / "rx_path.sv", RTL / "b96_core.sv",
            DESIGN / "sim" / "gth_wiz_model96.sv", DESIGN / "sim" / "tb_core.sv"] + xpm_free
    cocotb_run.run("b96_core", "tb_core", srcs, "core_cocotb", HERE, extra_env={"PYTHONPATH": str(ROOT)})


def test_rate_match_cocotb() -> None:
    srcs = [RTL / "rate_match.sv", DESIGN / "sim" / "tb_rate_match.sv"]
    cocotb_run.run("b96_rate_match", "tb_rate_match", srcs, "ratematch_cocotb", HERE, extra_env={"PYTHONPATH": str(ROOT)})


def test_rate_match_min_keep_1_shows_the_limit() -> None:
    """MIN_KEEP = 1 (delete only after an idle block was output): the minimum-gap stream at +300 ppm overflows, as design.md section 9 says."""
    srcs = [RTL / "rate_match.sv", DESIGN / "sim" / "tb_rate_match.sv"]
    cocotb_run.run("b96_rate_match_k1", "tb_rate_match", srcs, "ratematch_cocotb", HERE, parameters={"MIN_KEEP": 1}, testcase="minimum_gap_partner_faster",
                   extra_env={"PYTHONPATH": str(ROOT), "B96_RM_MIN_KEEP": "1"})


def test_ppm_partner_cocotb() -> None:
    """The core against a partner at +-ppm offsets (gth_wiz_model96p.sv). B96_PPM_RTL_ROOT picks the RTL tree (default: this one)."""
    import os
    root = Path(os.environ.get("B96_PPM_RTL_ROOT", str(DESIGN)))
    rtl = root / "rtl"
    names = ["b96_pkg.sv", "pcs_tx.sv", "pcs_rx.sv", "mac64_tx.sv", "mac64_rx.sv", "hs_vec.sv", "frame_src.sv", "trade64.sv", "rate_match.sv", "tx_path.sv",
             "rx_path.sv", "b96_core.sv"]
    srcs = [rtl / n for n in names if (rtl / n).exists()] + [DESIGN / "sim" / "gth_wiz_model96p.sv", DESIGN / "sim" / "tb_core_p.sv"]
    cocotb_run.run("b96_ppm", "tb_core_p", srcs, "ppm_cocotb", HERE, extra_env={"PYTHONPATH": str(ROOT), **{k: v for k, v in os.environ.items() if k.startswith("B96_PPM")}})
