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


CORE_SRCS = ["b96_pkg.sv", "pcs_tx.sv", "pcs_rx.sv", "mac64_tx.sv", "mac64_rx.sv", "hs_vec.sv", "frame_src.sv", "trade64.sv", "rate_match.sv", "rate_match_gp.sv", "tx_path.sv",
             "rx_path.sv", "rx_path_legacy.sv", "b96_core.sv"]


def test_core_cocotb() -> None:
    """RATE_MATCH = 1: brief 96C's elastic buffer (tests/core_cocotb.py)."""
    srcs = [RTL / n for n in CORE_SRCS] + [DESIGN / "sim" / "gth_wiz_model96.sv", DESIGN / "sim" / "tb_core.sv"]
    cocotb_run.run("b96_core", "tb_core", srcs, "core_cocotb", HERE, parameters={"RATE_MATCH": 1}, extra_env={"PYTHONPATH": str(ROOT)})


def test_core_cocotb_rm_own() -> None:
    """RATE_MATCH = 1 with brief 96E's own gray-pointer buffer (RM_OWN = 1): the same whole-core bench (tests/core_cocotb.py)."""
    srcs = [RTL / n for n in CORE_SRCS] + [DESIGN / "sim" / "gth_wiz_model96.sv", DESIGN / "sim" / "tb_core.sv"]
    cocotb_run.run("b96_core_own", "tb_core", srcs, "core_cocotb", HERE, parameters={"RATE_MATCH": 1, "RM_OWN": 1}, extra_env={"PYTHONPATH": str(ROOT)})


def test_core_cocotb_default_rate_match_off() -> None:
    """RATE_MATCH = 0, the default: the 97C receive path, held to 97C's own bench (tests/core_cocotb_default.py: main 6909e43f's, paths moved)."""
    srcs = [RTL / n for n in CORE_SRCS] + [DESIGN / "sim" / "gth_wiz_model96.sv", DESIGN / "sim" / "tb_core.sv"]
    cocotb_run.run("b96_core_default", "tb_core", srcs, "core_cocotb_default", HERE, parameters={"RATE_MATCH": 0}, extra_env={"PYTHONPATH": str(ROOT)})


def test_rate_match_cocotb() -> None:
    srcs = [RTL / "rate_match.sv", RTL / "rate_match_gp.sv", DESIGN / "sim" / "tb_rate_match.sv"]
    cocotb_run.run("b96_rate_match", "tb_rate_match", srcs, "ratematch_cocotb", HERE, extra_env={"PYTHONPATH": str(ROOT)})


def test_rate_match_gp_cocotb() -> None:
    """Brief 96E: rtl/rate_match_gp.sv (own gray-pointer buffer, HI = 1) against its twin, output for output, and the same frame checks, on the 96C scenarios."""
    srcs = [RTL / "rate_match.sv", RTL / "rate_match_gp.sv", DESIGN / "sim" / "tb_rate_match.sv"]
    cocotb_run.run("b96_rate_match_gp", "tb_rate_match", srcs, "ratematch_cocotb", HERE, parameters={"IMPL": 1, "HI": 1},
                   extra_env={"PYTHONPATH": str(ROOT), "B96_RM_IMPL": "gp", "B96_RM_HI": "1"})


def test_rate_match_gp_direct_read_cocotb() -> None:
    """Brief 96E: the ENT_SYNC = 0 variant of rate_match_gp (the reader reads the entry flops directly; build rm_gp_direct) against its twin."""
    srcs = [RTL / "rate_match.sv", RTL / "rate_match_gp.sv", DESIGN / "sim" / "tb_rate_match.sv"]
    cocotb_run.run("b96_rate_match_gp_direct", "tb_rate_match", srcs, "ratematch_cocotb", HERE, parameters={"IMPL": 1, "HI": 1, "ENT_SYNC": 0},
                   extra_env={"PYTHONPATH": str(ROOT), "B96_RM_IMPL": "gp", "B96_RM_HI": "1", "B96_RM_ENT_SYNC": "0"})


def test_rate_match_min_keep_1_shows_the_limit() -> None:
    """MIN_KEEP = 1 (delete only after an idle block was output): the minimum-gap stream at +300 ppm overflows, as design.md section 9 says."""
    srcs = [RTL / "rate_match.sv", RTL / "rate_match_gp.sv", DESIGN / "sim" / "tb_rate_match.sv"]
    cocotb_run.run("b96_rate_match_k1", "tb_rate_match", srcs, "ratematch_cocotb", HERE, parameters={"MIN_KEEP": 1}, testcase="minimum_gap_partner_faster",
                   extra_env={"PYTHONPATH": str(ROOT), "B96_RM_MIN_KEEP": "1"})


def test_ppm_partner_cocotb() -> None:
    """The core against a partner at +-ppm offsets (gth_wiz_model96p.sv). B96_PPM_RTL_ROOT picks the RTL tree (default: this one)."""
    import os
    root = Path(os.environ.get("B96_PPM_RTL_ROOT", str(DESIGN)))
    rtl = root / "rtl"
    names = ["b96_pkg.sv", "pcs_tx.sv", "pcs_rx.sv", "mac64_tx.sv", "mac64_rx.sv", "hs_vec.sv", "frame_src.sv", "trade64.sv", "rate_match.sv", "rate_match_gp.sv", "tx_path.sv",
             "rx_path.sv", "rx_path_legacy.sv", "b96_core.sv"]
    srcs = [rtl / n for n in names if (rtl / n).exists()] + [DESIGN / "sim" / "gth_wiz_model96p.sv", DESIGN / "sim" / "tb_core_p.sv"]
    cocotb_run.run("b96_ppm", "tb_core_p", srcs, "ppm_cocotb", HERE, extra_env={"PYTHONPATH": str(ROOT), **{k: v for k, v in os.environ.items() if k.startswith("B96_PPM")}})


def test_eyescan_cocotb() -> None:
    """Brief 96D: DRP access and the eye-scan point sequencer (EYESCAN = 1, RATE_MATCH = 0) against the Python twin and the GT's DRP stand-in."""
    srcs = [RTL / n for n in CORE_SRCS + ["es_ctrl.sv"]] + [DESIGN / "sim" / "gth_wiz_model96.sv", DESIGN / "sim" / "tb_core.sv"]
    cocotb_run.run("b96_eyescan", "tb_core", srcs, "eyescan_cocotb", HERE, parameters={"RATE_MATCH": 0, "EYESCAN": 1}, extra_env={"PYTHONPATH": str(ROOT)})


def test_eyescan_absent_by_default() -> None:
    """EYESCAN = 0 (the default): the new registers read 0 and the GT's DRP and drive ports are tied as before."""
    srcs = [RTL / n for n in CORE_SRCS + ["es_ctrl.sv"]] + [DESIGN / "sim" / "gth_wiz_model96.sv", DESIGN / "sim" / "tb_core.sv"]
    cocotb_run.run("b96_eyescan_off", "tb_core", srcs, "eyescan_cocotb", HERE, parameters={"RATE_MATCH": 0, "EYESCAN": 0}, testcase="eyescan_absent_reads_zero",
                   extra_env={"PYTHONPATH": str(ROOT), "B96_EYESCAN_OFF": "1"})
