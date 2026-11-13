"""ip_lib/crc32_step under cocotb + Icarus Verilog 12 against ip_lib/crc32_step/model.py (and zlib), both variants,
and the elaboration guard. HIL_RTL_CRC32_STEP points the tests at a seeded-fault copy of rtl/ (hil/ip_faults.py)."""
from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[3]
BLOCK = ROOT / "ip_lib" / "crc32_step"
TB = BLOCK / "tb"
BUILD = Path(os.environ.get("HIL_BUILD", ROOT / "build" / "hil_ip"))
IMPLS = ["word", "byte"]


def rtl_dir() -> Path:
    return Path(os.environ.get("HIL_RTL_CRC32_STEP", BLOCK / "rtl"))


@pytest.mark.parametrize("impl", IMPLS)
def test_variant(impl):
    build = BUILD / f"crc32_step_{impl}"
    r = get_runner("icarus")
    srcs = sorted(str(f) for f in rtl_dir().glob("*.sv"))
    params = {"IMPL": f'"{impl}"'}
    r.build(sources=srcs, hdl_toplevel="crc32_step", parameters=params, build_dir=build, timescale=("1ns", "1ps"),
            always=True, build_args=["-g2012"])
    env = {"PYTHONPATH": os.pathsep.join([str(ROOT), str(TB), os.environ.get("PYTHONPATH", "")]), "CRC32_IMPL": impl}
    res = r.test(test_module="crc32_step_cocotb", hdl_toplevel="crc32_step", build_dir=build, test_dir=TB,
                 parameters=params, extra_env=env, results_xml=str(build / "results.xml"), log_file=build / "sim.log",
                 timescale=("1ns", "1ps"))
    cases = list(ET.parse(res).getroot().iter("testcase"))
    bad = [c.get("name") for c in cases if c.find("failure") is not None or c.find("error") is not None]
    assert len(cases) == 2 and not bad, f"crc32_step {impl}: failed {bad} (log {build / 'sim.log'})"


def test_guard_rejects_out_of_space():
    vvp = BUILD / "guard_crc32_step.vvp"
    vvp.parent.mkdir(parents=True, exist_ok=True)
    srcs = sorted(str(f) for f in rtl_dir().glob("*.sv"))
    r = subprocess.run(["iverilog", "-g2012", "-o", str(vvp), "-s", "crc32_step", '-Pcrc32_step.IMPL="nibble"', *srcs],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = subprocess.run(["vvp", str(vvp)], capture_output=True, text=True)
    assert "ERROR" in out.stdout and "crc32_step:" in out.stdout, f"IMPL=nibble was accepted: {out.stdout}"
