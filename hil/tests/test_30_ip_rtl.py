"""Brief 30: the library instruments (ip_lib/{freq_duty_counter,frame_crc,dds_awg,logic_analyser,adc_histogram})
under cocotb + Icarus against the Python models in hil/instruments/models.py, at several points of each block's
parameter space. HIL_RTL_<BLOCK> points a block at a seeded-fault copy of its RTL (hil/ip_faults.py)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[2]
IP = ROOT / "ip_lib"
TB = ROOT / "hil" / "ip_tb"
BUILD = Path(os.environ.get("HIL_BUILD", ROOT / "build" / "hil_ip"))

CASES = [
    ("freq_duty_counter", {"GATE_CLKS": 2000, "CNT_W": 16}),
    ("freq_duty_counter", {"GATE_CLKS": 777, "CNT_W": 12}),
    ("frame_crc", {"PIX_W": 24}),
    ("frame_crc", {"PIX_W": 8}),
    ("frame_crc", {"PIX_W": 32}),
    ("dds_awg", {"PHASE_W": 32, "LUT_W": 8, "OUT_W": 16}),
    ("dds_awg", {"PHASE_W": 24, "LUT_W": 6, "OUT_W": 12}),
    ("logic_analyser", {"WIDTH": 16, "ADDR_W": 6}),
    ("logic_analyser", {"WIDTH": 8, "ADDR_W": 4}),
    ("adc_histogram", {"SAMP_W": 12, "BIN_W": 6, "CNT_W": 16}),
    ("adc_histogram", {"SAMP_W": 8, "BIN_W": 8, "CNT_W": 12}),
]


def run_case(block: str, params: dict, rtl_dir: Path | None = None, tag: str = "") -> None:
    d = rtl_dir or Path(os.environ.get(f"HIL_RTL_{block.upper()}", IP / block / "rtl"))
    name = f"{block}_{'_'.join(f'{k}{v}' for k, v in params.items())}{tag}"
    build = BUILD / name
    r = get_runner("icarus")
    r.build(sources=sorted(str(f) for f in d.glob("*.sv")), hdl_toplevel=block, parameters=params, build_dir=build,
            timescale=("1ns", "1ps"), always=True, build_args=["-g2012"])
    env = {"PYTHONPATH": os.pathsep.join([str(ROOT), str(TB), os.environ.get("PYTHONPATH", "")])}
    res = r.test(test_module="cocotb_ip30", hdl_toplevel=block, testcase=block, build_dir=build, test_dir=TB,
                 parameters=params, extra_env=env, results_xml=str(build / "results.xml"), log_file=build / "sim.log",
                 timescale=("1ns", "1ps"))
    import xml.etree.ElementTree as ET
    ran = [c for c in ET.parse(res).getroot().iter("testcase") if c.find("skipped") is None]
    bad = [c.get("name") for c in ran if c.find("failure") is not None or c.find("error") is not None]
    assert [c.get("name") for c in ran] == [block], f"{block}: ran {[c.get('name') for c in ran]}"
    assert not bad, f"{block} {params}: failed {bad}"


@pytest.mark.parametrize("block,params", CASES, ids=[f"{b}-{'-'.join(f'{k}{v}' for k, v in p.items())}" for b, p in CASES])
def test_block(block, params):
    run_case(block, params)


GUARDS = [
    ("freq_duty_counter", {"GATE_CLKS": 2}),
    ("freq_duty_counter", {"CNT_W": 40}),
    ("frame_crc", {"PIX_W": 12}),
    ("dds_awg", {"LUT_W": 2}),
    ("logic_analyser", {"ADDR_W": 1}),
    ("adc_histogram", {"BIN_W": 1}),
]


@pytest.mark.parametrize("block,params", GUARDS, ids=[f"{b}-{'-'.join(f'{k}{v}' for k, v in p.items())}" for b, p in GUARDS])
def test_guard_rejects_out_of_space(block, params):
    """An out-of-space parameter value must stop elaboration with the block's own $error."""
    import subprocess
    srcs = sorted(str(f) for f in (IP / block / "rtl").glob("*.sv"))
    vvp = BUILD / f"guard_{block}_{'_'.join(f'{k}{v}' for k, v in params.items())}.vvp"
    vvp.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["iverilog", "-g2012", "-o", str(vvp), "-s", block, *[f"-P{block}.{k}={v}" for k, v in params.items()], *srcs]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = subprocess.run(["vvp", str(vvp)], capture_output=True, text=True)
    assert f"ERROR" in out.stdout and f"{block}:" in out.stdout, f"{block} {params} was accepted: {out.stdout}"
