"""Brief 169: the prototype latency cuts (lat_cuts169: EARLY_MAC, FAST_PRE) under the 97C core bench (tests/core_cocotb_default.py, Icarus, 16 tests) in all four parameter combinations,
and the structural rules: the defaults are 0, and nothing of the base, lat_all3 or any open build is edited (every changed file is a copy under lat_cuts169/rtl).
The bench cannot run the bypass core (Icarus has no model of xpm_cdc_async_rst), so the base core b96_core.sv is patched in memory to pass the two parameters (the same two edits that
lat_cuts169/rtl/b96_core.sv carries); its behaviour with the bypass is covered by results/b169/core_sim.sh (xsim, real XPM macros)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]
RTL, CUTS, ALL3 = DESIGN / "rtl", DESIGN / "lat_cuts169" / "rtl", DESIGN / "lat_all3" / "rtl"
CORE_SRCS = ["b96_pkg.sv", "pcs_tx.sv", "pcs_rx.sv", "mac64_tx.sv", "mac64_rx.sv", "hs_vec.sv", "frame_src.sv", "trade64.sv", "rate_match.sv", "rate_match_gp.sv", "tx_path.sv",
             "rx_path.sv", "rx_path_legacy.sv", "b96_core.sv"]
COMBOS = {"base": (0, 0), "early": (1, 0), "fast": (0, 1), "both": (1, 1)}


def _patched_core(out: Path) -> Path:
    t = (RTL / "b96_core.sv").read_text()
    t = t.replace("    parameter bit          GO_REG ", "    parameter bit          EARLY_MAC   = 1'b0,\n    parameter bit          FAST_PRE    = 1'b0,\n    parameter bit          GO_REG ", 1)
    t = t.replace("rx_path_legacy #(.NRXW(NRXW_OLD)) u_rx", "rx_path_legacy #(.NRXW(NRXW_OLD), .EARLY_MAC(EARLY_MAC)) u_rx", 1)
    lines = t.split("\n")
    seen = 0
    for i, ln in enumerate(lines):
        if "tx_path #(.NTXW(NTXW)) u_tx" in ln:
            seen += 1
            if seen == 2:                                   # the RATE_MATCH = 0 branch
                lines[i] = ln.replace("tx_path #(.NTXW(NTXW))", "tx_path #(.NTXW(NTXW), .FAST_PRE(FAST_PRE))")
    out.write_text("\n".join(lines))
    return out


def _tb(out: Path) -> Path:
    t = (DESIGN / "sim" / "tb_core.sv").read_text()
    t = t.replace("    parameter bit RM_DIRECT = 1'b0\n", "    parameter bit RM_DIRECT = 1'b0,\n    parameter bit EARLY_MAC = 1'b0,\n    parameter bit FAST_PRE = 1'b0\n", 1)
    t = t.replace(".RM_DIRECT(RM_DIRECT)) u (", ".RM_DIRECT(RM_DIRECT), .EARLY_MAC(EARLY_MAC), .FAST_PRE(FAST_PRE)) u (", 1)
    assert "FAST_PRE(FAST_PRE)" in t
    out.write_text(t)
    return out


@pytest.mark.parametrize("combo", list(COMBOS))
def test_core_cocotb_default_with_cuts(combo: str, tmp_path: Path) -> None:
    e, f = COMBOS[combo]
    # sources: the base files, then lat_all3's trade64/tx_path (what lat_all3_bypass uses), then lat_cuts169's copies; b96_core is the base core patched to take the two parameters
    pick = lambda n: next(d / n for d in (CUTS, ALL3, RTL) if (d / n).is_file())     # noqa: E731
    srcs = [pick(n) for n in CORE_SRCS if n != "b96_core.sv"] + [_patched_core(tmp_path / "b96_core.sv")]
    srcs = [tmp_path / "b96_core.sv" if s.name == "b96_core.sv" else s for s in srcs]
    srcs += [DESIGN / "sim" / "gth_wiz_model96.sv", _tb(tmp_path / "tb_core.sv")]
    cocotb_run.run(f"b169_core_{combo}", "tb_core", srcs, "core_cocotb_default", HERE,
                   parameters={"RATE_MATCH": 0, "EARLY_MAC": e, "FAST_PRE": f}, extra_env={"PYTHONPATH": str(ROOT), "B169_WI_SHIFT": str(e)})     # with EARLY_MAC the word index runs one clock ahead: the poison tests inject by index


def test_defaults_are_off_and_files_are_copies() -> None:
    for name, pat in [("mac64_rx.sv", r"parameter bit EARLY = 1'b0"), ("trade64.sv", r"parameter bit EARLY = 1'b0"), ("rx_path_legacy.sv", r"parameter bit EARLY_MAC = 1'b0"),
                      ("mac64_tx.sv", r"parameter bit FAST_PRE = 1'b0"), ("pcs_tx.sv", r"parameter bit FAST = 1'b0"), ("frame_src.sv", r"parameter bit FAST = 1'b0"),
                      ("tx_path.sv", r"parameter bit FAST_PRE = 1'b0"), ("b96_core.sv", r"parameter bit\s+EARLY_MAC\s+= 1'b0"), ("b96_core.sv", r"parameter bit\s+FAST_PRE\s+= 1'b0")]:
        assert re.search(pat, (CUTS / name).read_text()), (name, pat)
    # every file under lat_cuts169/rtl has a parent it is a copy of; no parent was edited (the parents are what lat_all3_bypass builds with)
    parents = {"mac64_rx.sv": RTL, "mac64_tx.sv": RTL, "pcs_tx.sv": RTL, "frame_src.sv": RTL, "rx_path_legacy.sv": RTL, "trade64.sv": ALL3, "tx_path.sv": ALL3,
               "b96_core.sv": DESIGN / "rm_gp_bypass" / "rtl"}
    assert {p.name for p in CUTS.glob("*.sv")} == set(parents)
    for n, d in parents.items():
        assert (d / n).is_file()
        # the copy keeps every line of its parent except the lines this brief changed: no parent line is missing without a trace of the brief's number in the copy
        old, new = (d / n).read_text().splitlines(), (CUTS / n).read_text().splitlines()
        kept = sum(1 for ln in old if ln in set(new))
        assert kept >= len(old) - 25, (n, len(old) - kept)
        assert "169" in (CUTS / n).read_text() or n == "rx_path_legacy.sv"
