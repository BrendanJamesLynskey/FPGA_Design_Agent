"""Verilator -Wall on build rm_gp_ml (the sources of its build.yaml, the GT stand-in of the base design's lint directory); skipped where Verilator is not installed (CI installs it)."""
from __future__ import annotations

import glob
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

D = Path(__file__).resolve().parents[1]
ROOT = D.parents[2]
BASE = D.parent


@pytest.mark.skipif(shutil.which("verilator") is None, reason="Verilator not installed")
def test_build_rm_gp_ml_lints_clean() -> None:
    cfg = yaml.safe_load((D / "build.yaml").read_text())
    srcs = [f for g in cfg["sources"] for f in sorted(glob.glob(str(ROOT / g)))]
    stubs = sorted(glob.glob(str(BASE / "lint" / "*.sv")))
    vlt = sorted(glob.glob(str(BASE / "lint" / "*.vlt")))
    r = subprocess.run(["verilator", "--lint-only", "-Wall", "--top-module", cfg["top"], *vlt, *stubs, *srcs], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr[-3000:]


def test_the_build_swaps_exactly_the_files_that_have_a_marked_copy() -> None:
    """rm_gp_ml's source list is rm_gp's with the copies in rm_gp_ml/rtl in place of trade64, rx_path, rx_path_legacy and b96_core, plus ml_pkg, ml_stage and the brief 87 gbt_comb."""
    a = yaml.safe_load((D / "build.yaml").read_text())["sources"]
    b = yaml.safe_load((BASE / "rm_gp" / "build.yaml").read_text())["sources"]
    swapped = {f"designs/b96_kr260_10g/rtl/{n}.sv" for n in ("trade64", "rx_path", "rx_path_legacy", "b96_core")}
    added = {"designs/b96_kr260_10g/rm_gp_ml/rtl/ml_pkg.sv", "designs/b96_kr260_10g/rm_gp_ml/rtl/ml_stage.sv", "designs/b87_ml_trading/rtl/gen/gbt_comb.sv"}
    expect = {f.replace("/rtl/", "/rm_gp_ml/rtl/") if f in swapped else f for f in b} | added
    assert set(a) == expect
    gen_a = yaml.safe_load((D / "build.yaml").read_text())["generics"]
    assert gen_a == yaml.safe_load((BASE / "rm_gp" / "build.yaml").read_text())["generics"]
