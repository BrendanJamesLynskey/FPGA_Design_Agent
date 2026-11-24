"""Verilator -Wall lint of ddr2_sched and ddr2_addrmap (brief 141); skipped where Verilator is not installed."""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
D = HERE.parent
sys.path.insert(0, str(HERE))
import m141_measure as measure  # noqa: E402
import m141_timing as timing  # noqa: E402

RTL = D / "rtl"


@pytest.mark.skipif(shutil.which("verilator") is None, reason="no verilator (CI installs it)")
@pytest.mark.parametrize("top", ["ddr2_sched", "ddr2_addrmap"])
def test_verilator_wall_clean(top):
    import subprocess
    r = subprocess.run(["verilator", "--lint-only", "-Wall", "--top-module", top, str(RTL / "ddr2_sched.sv"), str(RTL / "ddr2_addrmap.sv")], capture_output=True, text=True)
    assert r.returncode == 0 and "%Warning" not in r.stderr, r.stderr
