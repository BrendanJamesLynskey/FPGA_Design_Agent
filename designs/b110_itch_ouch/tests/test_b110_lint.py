"""Verilator -Wall lint of the whole path at the default and at three other parameter points (brief 110, flow/lint.sh's rules for a design without a board top)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

DESIGN = Path(__file__).parent.parent
VERILATOR = shutil.which("verilator") or str(Path.home() / ".local/opt/verilator-5048/root/usr/share/verilator/bin/verilator")


@pytest.mark.skipif(not (shutil.which("verilator") or Path(VERILATOR).exists()), reason="Verilator not installed")
@pytest.mark.parametrize("params", [[], ["-GN_INST=2", "-GLEVELS=4", "-GORD_AW=5"], ["-GN_INST=3", "-GLEVELS=4", "-GORD_AW=6"], ["-GN_INST=8", "-GLEVELS=8", "-GORD_AW=10"]])
def test_lint_clean(params) -> None:
    srcs = [str(DESIGN / "lint" / "lint_waivers.vlt"), str(DESIGN / "rtl" / "itch_pkg.sv")] + sorted(str(p) for p in (DESIGN / "rtl").glob("*.sv") if p.name != "itch_pkg.sv")
    env = dict(os.environ)
    root = Path.home() / ".local/opt/verilator-5048/root/usr/share/verilator"
    if not shutil.which("verilator") and root.exists():
        env["VERILATOR_ROOT"] = str(root)
    r = subprocess.run([VERILATOR, "--lint-only", "-Wall", *params, "--top-module", "itch_ouch_top", *srcs], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "%Warning" not in r.stderr, r.stderr[-2000:]
