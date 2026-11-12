"""Brief 63A: ip_lib/fir under cocotb + Icarus Verilog 12 against ip_lib/fir/model.py, every variant at several points
of the parameter space, the differential test across all variants, and the elaboration guards. HIL_RTL_FIR points
the tests at a seeded-fault copy of rtl/ (hil/ip_faults.py)."""
from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[3]
FIR = ROOT / "ip_lib" / "fir"
TB = FIR / "tb"
BUILD = Path(os.environ.get("HIL_BUILD", ROOT / "build" / "hil_ip"))

POINTS = [
    {"TAPS": 16, "DATA_W": 16, "COEF_W": 16, "FOLD": 4},    # the default point
    {"TAPS": 7, "DATA_W": 12, "COEF_W": 10, "FOLD": 3},     # FOLD does not divide TAPS: one padding tap
    {"TAPS": 33, "DATA_W": 18, "COEF_W": 18, "FOLD": 8},    # five MAC engines: an uneven adder tree
    {"TAPS": 2, "DATA_W": 4, "COEF_W": 4, "FOLD": 2},       # the smallest point
]
IMPLS = ["dsp_bram", "dist_ram", "serial", "lut_mult"]
CASES = [(i, p) for p in POINTS for i in IMPLS]


def rtl_dir() -> Path:
    return Path(os.environ.get("HIL_RTL_FIR", FIR / "rtl"))


def _run(top: str, testcase: str, params: dict, name: str, extra_src=(), env=None):
    build = BUILD / name
    r = get_runner("icarus")
    srcs = sorted(str(f) for f in rtl_dir().glob("*.sv")) + [str(s) for s in extra_src]
    r.build(sources=srcs, hdl_toplevel=top, parameters=params, build_dir=build, timescale=("1ns", "1ps"),
            always=True, build_args=["-g2012"])
    e = {"PYTHONPATH": os.pathsep.join([str(ROOT), str(TB), os.environ.get("PYTHONPATH", "")]), **(env or {})}
    res = r.test(test_module="cocotb_fir", hdl_toplevel=top, testcase=testcase, build_dir=build, test_dir=TB,
                 parameters=params, extra_env=e, results_xml=str(build / "results.xml"), log_file=build / "sim.log",
                 timescale=("1ns", "1ps"))
    ran = [c for c in ET.parse(res).getroot().iter("testcase") if c.find("skipped") is None]
    bad = [c.get("name") for c in ran if c.find("failure") is not None or c.find("error") is not None]
    assert [c.get("name") for c in ran] == [testcase], f"ran {[c.get('name') for c in ran]}"
    assert not bad, f"{name}: failed {bad} (log {build / 'sim.log'})"


def _id(p: dict) -> str:
    return "-".join(f"{k}{v}" for k, v in p.items())


@pytest.mark.parametrize("impl,params", CASES, ids=[f"{i}-{_id(p)}" for i, p in CASES])
def test_variant(impl, params):
    _run("fir", "fir_variant", {"IMPL": f'"{impl}"', **params}, f"fir_{impl}_{_id(params)}", env={"FIR_IMPL": impl})


@pytest.mark.parametrize("params", POINTS[:3], ids=[_id(p) for p in POINTS[:3]])
def test_differential(params):
    _run("fir_diff_tb", "fir_diff", params, f"fir_diff_{_id(params)}", extra_src=[TB / "fir_diff_tb.sv"])


GUARDS = [
    {"IMPL": '"fast"'},
    {"TAPS": 1, "FOLD": 1},
    {"FOLD": 32},                                    # more than TAPS
    {"DATA_W": 25},
    {"COEF_W": 19},
    {"DATA_W": 24, "COEF_W": 18, "TAPS": 256, "FOLD": 8},     # ACC_W 50 > 48
    {"IMPL": '"lut_mult"', "TAPS": 65},
]


@pytest.mark.parametrize("params", GUARDS, ids=[_id(p).replace('"', "") for p in GUARDS])
def test_guard_rejects_out_of_space(params):
    """An out-of-space parameter value must stop elaboration with the block's own $error."""
    vvp = BUILD / f"guard_fir_{_id(params).replace(chr(34), '')}.vvp"
    vvp.parent.mkdir(parents=True, exist_ok=True)
    srcs = sorted(str(f) for f in rtl_dir().glob("*.sv"))
    cmd = ["iverilog", "-g2012", "-o", str(vvp), "-s", "fir", *[f"-Pfir.{k}={v}" for k, v in params.items()], *srcs]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = subprocess.run(["vvp", str(vvp)], capture_output=True, text=True)
    assert "ERROR" in out.stdout and "fir:" in out.stdout, f"{params} was accepted: {out.stdout}"
