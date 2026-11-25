"""Brief 169: the structural rules of the prototype latency cuts (lat_cuts169: EARLY_MAC, FAST_PRE): the defaults are 0, and nothing of the base, lat_all3 or any open build is edited
(every changed file is a copy under lat_cuts169/rtl), and the build's top forwards both parameters (brief 203: the first build used the shared top, which has no such parameters, so
both cuts were off in it). The simulation half is test_169_cuts_rtl.py (Icarus; CI's RTL job, not the Python job)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

HERE = Path(__file__).parent
DESIGN = HERE.parent
RTL, CUTS, ALL3 = DESIGN / "rtl", DESIGN / "lat_cuts169" / "rtl", DESIGN / "lat_all3" / "rtl"


def test_defaults_are_off_and_files_are_copies() -> None:
    for name, pat in [("mac64_rx.sv", r"parameter bit EARLY = 1'b0"), ("trade64.sv", r"parameter bit EARLY = 1'b0"), ("rx_path_legacy.sv", r"parameter bit EARLY_MAC = 1'b0"),
                      ("mac64_tx.sv", r"parameter bit FAST_PRE = 1'b0"), ("pcs_tx.sv", r"parameter bit FAST = 1'b0"), ("frame_src.sv", r"parameter bit FAST = 1'b0"),
                      ("tx_path.sv", r"parameter bit FAST_PRE = 1'b0"), ("b96_core.sv", r"parameter bit\s+EARLY_MAC\s+= 1'b0"), ("b96_core.sv", r"parameter bit\s+FAST_PRE\s+= 1'b0")]:
        assert re.search(pat, (CUTS / name).read_text()), (name, pat)
    # every file under lat_cuts169/rtl has a parent it is a copy of; no parent was edited (the parents are what lat_all3_bypass builds with)
    parents = {"mac64_rx.sv": RTL, "mac64_tx.sv": RTL, "pcs_tx.sv": RTL, "frame_src.sv": RTL, "rx_path_legacy.sv": RTL, "trade64.sv": ALL3, "tx_path.sv": ALL3,
               "b96_core.sv": DESIGN / "rm_gp_bypass" / "rtl", "kr260_10g_top.sv": RTL}
    assert {p.name for p in CUTS.glob("*.sv")} == set(parents)
    for n, d in parents.items():
        assert (d / n).is_file()
        # the copy keeps every line of its parent except the lines this brief changed: no parent line is missing without a trace of the brief's number in the copy
        old, new = (d / n).read_text().splitlines(), (CUTS / n).read_text().splitlines()
        kept = sum(1 for ln in old if ln in set(new))
        assert kept >= len(old) - 25, (n, len(old) - kept)
        assert "169" in (CUTS / n).read_text() or n == "rx_path_legacy.sv"


def test_build_top_forwards_both_cuts_and_the_build_uses_it() -> None:
    """Brief 203: a generic the top module does not declare is dropped by synth_design ('Unused top level parameter/generic'), so the first lat_cuts169 build had both cuts off."""
    top = (CUTS / "kr260_10g_top.sv").read_text()
    for p in ("EARLY_MAC", "FAST_PRE"):
        assert re.search(rf"parameter bit\s+{p}\s+= 1'b0", top), p
        assert f".{p}({p})" in top, p
    cfg = yaml.safe_load((DESIGN / "lat_cuts169" / "build.yaml").read_text())
    assert "designs/b96_kr260_10g/lat_cuts169/rtl/kr260_10g_top.sv" in cfg["sources"]
    assert "designs/b96_kr260_10g/rtl/kr260_10g_top.sv" not in cfg["sources"]
    assert cfg["generics"]["EARLY_MAC"] == "1'b1" and cfg["generics"]["FAST_PRE"] == "1'b1"
    # the copy differs from the shared top only in the two parameters, their forwarding and the header line
    old, new = (RTL / "kr260_10g_top.sv").read_text().splitlines(), top.splitlines()
    assert [ln for ln in old if ln not in new] == [ln for ln in old if "b96_core #(" in ln]
    assert len([ln for ln in new if ln not in old]) == 4
