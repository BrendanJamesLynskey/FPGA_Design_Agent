"""Verilator -Wall lint of the latency probe (brief 191). The image's top is not linted here: it instantiates the processor system IP, which is not available to Verilator."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

DESIGN = Path(__file__).parent.parent
VERILATOR = shutil.which("verilator") or str(Path.home() / ".local/opt/verilator-5048/root/usr/share/verilator/bin/verilator")


@pytest.mark.skipif(not (shutil.which("verilator") or Path(VERILATOR).exists()), reason="Verilator not installed")
@pytest.mark.parametrize("params", [[], ["-GID_W=4", "-GLOG_DEPTH=16"]])
def test_lint_clean(params) -> None:
    env = dict(os.environ)
    root = Path.home() / ".local/opt/verilator-5048/root/usr/share/verilator"
    if not shutil.which("verilator") and root.exists():
        env["VERILATOR_ROOT"] = str(root)
    r = subprocess.run([VERILATOR, "--lint-only", "-Wall", *params, "--top-module", "axi_lat_probe", str(DESIGN / "rtl" / "axi_lat_probe.sv")], capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "%Warning" not in r.stderr, r.stderr[-2000:]
