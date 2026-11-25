"""ip_lib/jtag_regs under cocotb + Icarus Verilog 12: the common register map (jtag_regs_map). jtag_bus (BSCANE2, xpm_cdc) needs Xilinx
models; its register port and CDC are covered by designs/b58a_trigger and the board run of 2026-11-17."""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

from cocotb_tools.runner import get_runner

ROOT = Path(__file__).resolve().parents[3]
BLOCK = ROOT / "ip_lib" / "jtag_regs"
TB = BLOCK / "tb"
BUILD = Path(os.environ.get("HIL_BUILD", ROOT / "build" / "hil_ip")) / "jtag_regs_map"


def test_common_map():
    r = get_runner("icarus")
    params = {"DESIGN_ID": "32'h20920001"}
    r.build(sources=[str(BLOCK / "rtl" / "jtag_regs_map.sv")], hdl_toplevel="jtag_regs_map", parameters=params, build_dir=BUILD,
            timescale=("1ns", "1ps"), always=True, build_args=["-g2012"])
    res = r.test(test_module="jtag_regs_map_cocotb", hdl_toplevel="jtag_regs_map", build_dir=BUILD, test_dir=TB, parameters=params,
                 extra_env={"PYTHONPATH": os.pathsep.join([str(TB), os.environ.get("PYTHONPATH", "")])},
                 results_xml=str(BUILD / "results.xml"), log_file=BUILD / "sim.log", timescale=("1ns", "1ps"))
    cases = list(ET.parse(res).getroot().iter("testcase"))
    bad = [c.get("name") for c in cases if c.find("failure") is not None or c.find("error") is not None]
    assert len(cases) == 3 and not bad, f"jtag_regs_map: failed {bad} (log {BUILD / 'sim.log'})"
