"""Brief 100: the parts of the RapidWright capabilities that need neither RapidWright nor Vivado (CI has neither): the pin, the block-path
analysis, and the RTL (Verilator lint of the wrappers). Tests that need RapidWright skip with a notice when it is not installed."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from flow import rapidwright_pin as pin

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]


def test_pin_is_consistent():
    assert pin.RAPIDWRIGHT_VERSION.startswith(pin.VIVADO_VERSION + ".")       # RapidWright releases follow the Vivado release
    assert len(pin.WHEEL_SHA256) == 64 and len(pin.JAR_SHA256) == 64
    assert pin.argv("x.py", "a")[1:] == ["-I", "x.py", "a"]
    assert pin.env()["JAVA_HOME"] == str(pin.JAVA_HOME)


def test_available_says_why():
    ok, why = pin.available()
    assert ok or "RapidWright venv not installed" in why or "no Java" in why
    if not ok:
        pytest.skip(f"RapidWright is not installed here: {why}")


def test_analyse_blocks(tmp_path):
    csv_a = tmp_path / "a.csv"
    csv_a.write_text("copy,endpoint,data_path_delay_ns,slack_ns,logic_levels\n"
                     "0,r1/D,1.000,0.5,2\n0,r2/D,2.000,0.4,3\n1,r1/D,1.000,0.5,2\n1,r2/D,2.010,0.3,3\n")
    out = tmp_path / "s.json"
    r = subprocess.run([sys.executable, str(HERE / "scripts" / "analyse_blocks.py"), str(out), f"x={csv_a}"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    c1 = json.loads(out.read_text())["x"]["copies"]["1"]
    assert c1["endpoints_identical"] == 1 and c1["max_abs_diff_ps"] == 10 and c1["worst_delay_ns"] == 2.01


def test_wrappers_lint():
    vl = shutil.which("verilator")
    if not vl:
        pytest.skip("Verilator not installed")
    b96 = ROOT / "designs" / "b96_kr260_10g" / "rtl"
    r = subprocess.run([vl, "--lint-only", "-Wall", "-Wno-fatal", "--top-module", "reloc_top",
                        str(b96 / "b96_pkg.sv"), str(b96 / "pcs_tx.sv"), str(HERE / "rtl" / "pcs_tx_blk.sv"), str(HERE / "rtl" / "reloc_top.sv")],
                       capture_output=True, text=True)
    assert "%Error" not in r.stderr, r.stderr[-2000:]         # warnings are reported by brief 96's own lint; this checks that the wrappers elaborate
