#!/usr/bin/env python3
"""Brief 55: collect the out-of-context block runs (tools/vhdl_block_synth.tcl) into results/55_vhdl/blocks.json.

    python3 results/55_vhdl/collect_blocks.py <dir holding one sub-directory per block run>
LUT/FF from utilization.rpt (Slice LUTs, Slice Registers), worst setup slack from summary.txt, and the brief 16 CDC structure
verdict (flow/cdc_structure.py) where the block has two clocks."""
import json, re, sys
from pathlib import Path

out = {}
for d in sorted(Path(sys.argv[1]).iterdir()):
    u = (d / "utilization.rpt").read_text() if (d / "utilization.rpt").is_file() else ""
    s = dict(l.split(" ", 1) for l in (d / "summary.txt").read_text().splitlines()) if (d / "summary.txt").is_file() else {}
    lut = re.search(r"\| Slice LUTs\*?\s*\|\s*(\d+)", u)
    ff = re.search(r"\| Slice Registers\s*\|\s*(\d+)", u)
    r = {"vivado": s.get("vivado"), "lut": int(lut.group(1)) if lut else None, "ff": int(ff.group(1)) if ff else None,
         "lutram_cells": int(s["lutram"]) if "lutram" in s else None, "wns_ns": float(s["wns_ns"]) if "wns_ns" in s else None}
    cj = d / "cdc_structure.json"
    if cj.is_file():
        c = json.loads(cj.read_text())
        r["cdc_gate"] = "pass" if c.get("pass") else "FAIL"
        r["cdc_unsafe"] = len(c.get("unsafe") or [])
    out[d.name] = r
p = Path(__file__).with_name("blocks.json")
p.write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
