"""Verilator -Wall lint of the TCP fast path with brief 110's frame builder (brief 119, flow/lint.sh's rules for a design without a board top)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

DESIGN = Path(__file__).parent.parent
VERILATOR = shutil.which("verilator") or str(Path.home() / ".local/opt/verilator-5048/root/usr/share/verilator/bin/verilator")


@pytest.mark.skipif(not (shutil.which("verilator") or Path(VERILATOR).exists()), reason="Verilator not installed")
def test_lint_clean() -> None:
    srcs = [str(DESIGN / "lint" / "lint_waivers.vlt"), str(DESIGN.parent / "b110_itch_ouch" / "rtl" / "ouch_enter.sv"), str(DESIGN / "rtl" / "tcp_fast.sv")]
    env = dict(os.environ)
    root = Path.home() / ".local/opt/verilator-5048/root/usr/share/verilator"
    if not shutil.which("verilator") and root.exists():
        env["VERILATOR_ROOT"] = str(root)
    r = subprocess.run([VERILATOR, "--lint-only", "-Wall", "--top-module", "tcp_fast", *srcs], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "%Warning" not in r.stderr, r.stderr[-3000:]
