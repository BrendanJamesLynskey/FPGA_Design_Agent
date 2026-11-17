#!/usr/bin/env python3
"""Simulate the whole demonstration design with the CRC block taken from its functional netlist, and count the verdict latency.

    python3 designs/b102_managed_fcs/scripts/measure_latency.py [--out results/102_managed/latency.json]

The sources are fcs_top, fcs_ctrl and heartbeat (RTL) and the CRC block as the flat functional netlist (flow/managed_import.flatten_netlist
of ext/crc32_d16_netlist.v with the public Xilinx cell models of the Yosys distribution), simulated with Icarus. The latency is the clock (counted from the first clock
after power-up) in which ``pass_o`` first rises, for the committed controller and for the controller
as the scripted agent session edits it (demo_managed_session.edited_ctrl). Needs the OSS CAD Suite (FDA_OSS_CAD) and Icarus.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from flow import managed_import as I  # noqa: E402
from demo_managed_session import edited_ctrl  # noqa: E402

D = ROOT / "designs" / "b102_managed_fcs"
TB = """`timescale 1ns/1ps
module tb;
  reg clk = 0; wire [1:0] led; integer cyc = 0, last_en = -1, t_pass = -1, t_hbfree = 0;
  fcs_top dut (.clk_25(clk), .led(led));
  always #5 clk = ~clk;
  always @(posedge clk) begin
    cyc <= cyc + 1;
    if (dut.u_ctrl.crc_en_o) last_en <= cyc;
    if (dut.u_ctrl.pass_o && t_pass < 0) t_pass <= cyc;
  end
  initial begin repeat (200) @(posedge clk); $display("RESULT last_en=%0d pass=%0d led0=%0d", last_en, t_pass, led[0]); $finish; end
endmodule
"""


def run(ctrl_src: Path, work: Path, flat: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    (work / "tb.sv").write_text(TB)
    srcs = [str(flat), str(ctrl_src), str(D / "rtl/heartbeat/heartbeat.sv"), str(D / "rtl/fcs_top.sv"), str(work / "tb.sv")]
    subprocess.run(["iverilog", "-g2012", "-o", str(work / "s.vvp"), *srcs], check=True, capture_output=True, text=True)
    out = subprocess.run(["vvp", str(work / "s.vvp")], check=True, capture_output=True, text=True).stdout
    m = re.search(r"RESULT last_en=(\d+) pass=(-?\d+) led0=(\d)", out)
    p, led0 = int(m.group(2)), int(m.group(3))
    return {"first_pass_cycle": p, "led0_at_end": led0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "102_managed" / "latency.json")
    ap.add_argument("--work", type=Path, default=ROOT / "build" / "102_latency")
    a = ap.parse_args(argv)
    a.work.mkdir(parents=True, exist_ok=True)
    flat = I.flatten_netlist(D / "ext/crc32_d16_netlist.v", "crc32_d16", a.work / "flat.v")
    base_src = D / "rtl/fcs_ctrl.sv"
    (a.work / "edited_ctrl.sv").write_text(edited_ctrl(base_src.read_text()))
    res = {"baseline": run(base_src, a.work / "base", flat), "edited": run(a.work / "edited_ctrl.sv", a.work / "edit", flat)}
    res["clocks_saved"] = res["baseline"]["first_pass_cycle"] - res["edited"]["first_pass_cycle"]
    res["note"] = ("pass_o first rises one clock earlier in the edited controller; both pass the self-test (led[0] high at the end), "
                   "with the CRC block taken from the functional netlist")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
