#!/usr/bin/env python3
"""Brief 243: simulate the bus path of the patched Red Pitaya top in xsim (Vivado). Not run in CI (needs xsim and the vendor checkout from tools/rp_shell.py).

    python3 hil/rp_bus_sim/run_xsim.py <workdir> [--blocks DIR] [--slot7 rp_freqcount --id7 0xFDA10101] [--slot6 rp_patgen --id6 0xFDA10201] [--no-adapter]

``<workdir>`` is a tools/rp_shell.py work directory (``vendor/`` at the pin). The blocks' RTL is taken from ``--blocks`` (default: the work directory's
``vendor/prj/fda_shell/rtl``, which is what the build used). ``--no-adapter`` wires the blocks straight to the shell's bus, as build 170300fd was, to show the failure.
Prints the testbench's lines and returns 0 on ``BUS PATH PASS``.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import rp_shell  # noqa: E402

VENDOR_FILES = ["interface/sys_bus_if.sv", "sys_bus_interconnect.sv", "sys_bus_cdc.sv", "sys_bus_stub.sv"]


def direct_instance(slot: int, module: str, inst: str, dac: str) -> str:
    """The wiring of build 170300fd: the block on the shell's slot bus, no adapter."""
    return (f"  {module} {inst} (.clk (adc_clk), .rstn (adc_rstn),\n"
            f"    .sys_addr (sys[{slot}].addr), .sys_wdata (sys[{slot}].wdata), .sys_wen (sys[{slot}].wen), .sys_ren (sys[{slot}].ren),\n"
            f"    .sys_rdata (sys[{slot}].rdata), .sys_err (sys[{slot}].err), .sys_ack (sys[{slot}].ack),\n"
            f"    .adc_a (adc_dat[0]), .adc_b (adc_dat[1]), .dac_a ({dac}[0]), .dac_b ({dac}[1]));\n")


def slots_text(slot7: str, slot6: str, adapter: bool) -> str:
    if adapter:
        return rp_shell.slot_instance(7, slot7, "i_user_block", "user_dac", "slot 7") + "\n" + rp_shell.slot_instance(6, slot6, "i_user6_block", "user6_dac", "slot 6") + "\n"
    return direct_instance(7, slot7, "i_user_block", "user_dac") + direct_instance(6, slot6, "i_user6_block", "user6_dac")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("workdir", type=Path)
    ap.add_argument("--blocks", type=Path)
    ap.add_argument("--slot7", default="rp_freqcount")
    ap.add_argument("--slot6", default="rp_patgen")
    ap.add_argument("--id7", default="32'hFDA10101")
    ap.add_argument("--id6", default="32'hFDA10201")
    ap.add_argument("--phase", default="1", help="adc_clk offset from the PS clock, ns (the clocks are the same 125 MHz from different buffers)")
    ap.add_argument("--no-adapter", action="store_true")
    ap.add_argument("--out", type=Path, help="write the testbench output here")
    a = ap.parse_args(argv)
    v = a.workdir / "vendor"
    blocks = a.blocks or v / "prj" / rp_shell.NEW_PRJ / "rtl"
    sim = a.workdir / ("sim_noadapt" if a.no_adapter else "sim")
    sim.mkdir(exist_ok=True)
    text = slots_text(a.slot7, a.slot6, not a.no_adapter)
    (sim / "slots.svh").write_text(text)
    xs = Path(os.environ.get("XSIM_BIN", "/opt/Xilinx/2025.2/Vivado/bin"))
    env = {**os.environ, "PATH": f"{xs}:{os.environ['PATH']}"}
    srcs = [v / "rtl" / "rtl" / f for f in VENDOR_FILES] + [rp_shell.ADAPT_DEFAULT] + sorted(p for p in Path(blocks).glob("*.sv") if p.name not in ("rp_user_block.sv",) and not p.name.startswith(("red_pitaya", "tb_")))
    top = ROOT / "hil" / "rp_bus_sim" / "tb_rp_bus_path.sv"
    defs = ["-d", f"ID6={a.id6}", "-d", f"ID7={a.id7}", "-d", f"PHASE={a.phase}"]
    def run(argv, **kw):
        return subprocess.run(argv, cwd=sim, env=env, capture_output=True, text=True, **kw)
    r = run(["xvlog", "-sv", *defs, "-i", str(sim), *map(str, srcs), str(top)])
    if r.returncode or "ERROR" in r.stdout:
        print(r.stdout[-3000:], r.stderr[-1000:]); return 2
    r = run(["xelab", "-debug", "typical", "tb_rp_bus_path", "-s", "bus", "-timescale", "1ns/1ps"])
    if r.returncode or "\nERROR" in r.stdout:
        print(r.stdout[-3000:], r.stderr[-1000:]); return 2
    r = run(["xsim", "bus", "-R"])
    lines = [l for l in r.stdout.splitlines() if l.startswith(("READ", "WRITE", "  FAIL", "ERRORS", "BUS PATH"))]
    print("\n".join(lines))
    if a.out:
        a.out.write_text("\n".join(lines) + "\n")
    return 0 if "BUS PATH PASS" in lines else 1


if __name__ == "__main__":
    sys.exit(main())
