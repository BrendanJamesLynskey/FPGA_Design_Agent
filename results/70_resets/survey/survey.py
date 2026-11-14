#!/usr/bin/env python3
"""Brief 70 Part 2a: reset style of AMD's unencrypted IP sources, counted by pattern (Vivado 2026.1 install).

    python3 results/70_resets/survey/survey.py [--root /opt/Xilinx/2026.1/Vivado/data/ip] [--out results/70_resets/records/ip_reset_survey.json]

Reads the install's HDL read-only and writes only counts and file names: no AMD text is copied. The counts are by
pattern (an approximation: a reset used through a function or a record is not seen); the table in the README says which
rows were also read by hand. Per IP it records:
  async_procs   clocked processes or always blocks whose sensitivity list holds the clock and a reset-named signal
  sync_resets   clocked blocks that test a reset-named signal under the clock edge
  level_tests   how the reset is tested ('1' = active high, '0' = active low) among the synchronous tests
  ports         reset-named ports and their direction
  cdc           reset or CDC macros and primitives instantiated (xpm_cdc_*, FDRE chains, SRL16)
  prims_async   FDCE/FDPE/FDRE-with-R/FDSE primitive instantiations by name
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

IPS = {
    "proc_sys_reset": "xilinx/proc_sys_reset_v5_0/hdl",
    "axi_gpio": "xilinx/axi_gpio_v2_0/hdl",
    "axi_uartlite": "xilinx/axi_uartlite_v2_0/hdl",
    "axi_timer": "xilinx/axi_timer_v2_0/hdl",
    "axi_intc": "xilinx/axi_intc_v4_1/hdl",
    "axi_iic": "xilinx/axi_iic_v2_1/hdl",
    "axi_quad_spi": "xilinx/axi_quad_spi_v3_2/hdl",
    "axi_dma": "xilinx/axi_dma_v7_1/hdl",
    "axi_cdma": "xilinx/axi_cdma_v4_1/hdl",
    "axi_lite_ipif (slave attachment used by the peripherals)": "xilinx/axi_lite_ipif_v3_1/hdl",
    "interrupt_control": "xilinx/interrupt_control_v3_2/hdl",
    "axi_datamover (inside DMA)": "xilinx/axi_datamover_v5_1/hdl",
    "axi_sg (inside DMA)": "xilinx/axi_sg_v4_1/hdl",
    "axi_register_slice": "xilinx/axi_register_slice_v2_1/hdl",
    "fifo_generator (synthesis wrapper)": "xilinx/fifo_generator_v13_2/hdl/fifo_generator_v13_2_syn_rfs.vhd",
    "xpm_cdc": "xpm/xpm_cdc/hdl",
    "xpm_fifo": "xpm/xpm_fifo/hdl",
    "xpm_memory": "xpm/xpm_memory/hdl",
}
RESET_NAME = r"(?:\w*(?:rst|reset|aresetn|rstn|clr|clear)\w*)"
VHDL_PROC = re.compile(r"process\s*\(([^)]*)\)", re.I)
VHDL_EDGE = re.compile(r"(?:rising_edge\s*\(\s*(\w+)\s*\)|(\w+)'event\s+and\s+\2\s*=\s*'1')", re.I)
SV_ALWAYS = re.compile(r"always(?:_ff)?\s*@\s*\(([^)]*)\)", re.I)
VHDL_TEST = re.compile(r"\bif\s*\(?\s*(" + RESET_NAME + r")\s*=\s*'([01])'", re.I)
SV_TEST = re.compile(r"\bif\s*\(\s*(!|~)?\s*(" + RESET_NAME + r")\s*(?:==\s*1'?b?([01]))?\s*\)", re.I)
PORT = re.compile(r"^\s*(" + RESET_NAME + r")\s*:\s*(in|out)\b", re.I | re.M)
SVPORT = re.compile(r"\b(input|output)\s+(?:wire\s+|logic\s+|reg\s+)?(?:\[[^\]]*\]\s*)?(" + RESET_NAME + r")\b", re.I)
PRIM = re.compile(r"\b(FDCE|FDPE|FDRE|FDSE|LDCE|LDPE)\b")
CDC = re.compile(r"\b(xpm_cdc_\w+|SRL16\w*|SRLC32E|SRLC16E|ASYNC_REG)\b", re.I)


def strip_vhdl(t: str) -> str:
    return re.sub(r"--[^\n]*", "", t)


def strip_sv(t: str) -> str:
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", t, flags=re.S)


def scan_file(p: Path) -> dict:
    raw = p.read_text(errors="replace")
    vhdl = p.suffix.lower() in (".vhd", ".vhdl")
    t = strip_vhdl(raw) if vhdl else strip_sv(raw)
    r = {"async_procs": 0, "sync_resets": 0, "level_tests": Counter(), "ports": Counter(), "cdc": Counter(),
         "prims": Counter()}
    names: set[str] = set()
    if vhdl:
        for m in VHDL_PROC.finditer(t):
            sens = [s.strip().lower() for s in m.group(1).split(",") if s.strip()]
            rst = [s for s in sens if re.fullmatch(RESET_NAME, s)]
            end = re.search(r"end\s+process", t[m.end():], re.I)
            body = t[m.end():m.end() + (end.start() if end else 900)]
            if len(sens) >= 2 and rst and VHDL_EDGE.search(body):
                r["async_procs"] += 1
                names.update(rst)
            elif VHDL_EDGE.search(body):
                e = VHDL_EDGE.search(body)
                tail = body[e.end():e.end() + 260]
                tm = VHDL_TEST.search(tail)
                if tm:
                    r["sync_resets"] += 1
                    r["level_tests"][tm.group(2)] += 1
                    names.add(tm.group(1).lower())
        for m in PORT.finditer(t):
            r["ports"][f"{m.group(1).lower()}:{m.group(2).lower()}"] += 1
    else:
        for m in SV_ALWAYS.finditer(t):
            sens = m.group(1).lower()
            if "posedge" in sens and re.search(r"(?:pos|neg)edge\s+" + RESET_NAME, sens):
                r["async_procs"] += 1
            elif "posedge" in sens:
                tail = t[m.end():m.end() + 240]
                tm = SV_TEST.search(tail)
                if tm:
                    r["sync_resets"] += 1
                    low = bool(tm.group(1)) or tm.group(3) == "0"
                    r["level_tests"]["0" if low else "1"] += 1
        for m in SVPORT.finditer(t):
            r["ports"][f"{m.group(2).lower()}:{m.group(1).lower()}"] += 1
    for m in PRIM.finditer(t):
        r["prims"][m.group(1)] += 1
    for m in CDC.finditer(t):
        r["cdc"][m.group(1).lower()] += 1
    r["names"] = sorted(names)
    return r


def survey(root: Path) -> dict:
    out = {}
    for ip, rel in IPS.items():
        base = root / rel
        files = [base] if base.is_file() else sorted(f for f in base.rglob("*")
                                                        if f.suffix.lower() in (".vhd", ".v", ".sv", ".vhdl"))
        agg = {"files": [str(f.relative_to(root)) for f in files], "async_procs": 0, "sync_resets": 0,
               "level_tests": Counter(), "ports": Counter(), "cdc": Counter(), "prims": Counter(), "names": set()}
        for f in files:
            r = scan_file(f)
            for k in ("async_procs", "sync_resets"):
                agg[k] += r[k]
            for k in ("level_tests", "ports", "cdc", "prims"):
                agg[k].update(r[k])
            agg["names"].update(r["names"])
        agg["names"] = sorted(agg["names"])
        for k in ("level_tests", "ports", "cdc", "prims"):
            agg[k] = dict(sorted(agg[k].items()))
        out[ip] = agg
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/opt/Xilinx/2026.1/Vivado/data/ip")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "records" / "ip_reset_survey.json"))
    a = ap.parse_args()
    res = survey(Path(a.root))
    Path(a.out).write_text(json.dumps({"vivado": "2026.1", "root": a.root, "ips": res}, indent=1, sort_keys=True) + "\n")
    for ip, d in res.items():
        print(f"{ip:38s} files={len(d['files']):2d} async={d['async_procs']:4d} sync={d['sync_resets']:4d} "
              f"levels={d['level_tests']} cdc={d['cdc']}")
