#!/usr/bin/env python3
"""Busy clocks per point and a cell checksum for each c13 core variant (tb_busy.sv, Icarus). Writes latency.json here.

    python3 results/62a_closure/latency/run_latency.py
"""
import json
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VARIANTS = {
    "original (fixture)": ROOT / "agent/tests/fixtures/closure/c13_orig/rtl/hough.sv",
    "hand fix (PR #134)": ROOT / "benchmark/course/tasks/c13_hough_lines/ref/rtl/hough.sv",
    "closure, no plan": HERE.parent / "c13_orig_noplan/rtl_final/hough.sv",
    "closure, with plan": HERE.parent / "c13_orig_plan/rtl_final/hough.sv",
    "unguarded run (invalid)": HERE.parent / "c13_orig_plan_unguarded/rtl_final/hough.sv",
}
rows = {}
for name, f in VARIANTS.items():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "sim.vvp"
        subprocess.run(["iverilog", "-g2012", "-o", str(out), str(HERE / "tb_busy.sv"), str(f)], check=True)
        text = subprocess.run(["vvp", "-n", str(out)], capture_output=True, text=True, check=True).stdout
    m = re.search(r"BUSY_CLOCKS_PER_POINT (\d+) CHECKSUM (-?\d+)", text)
    rows[name] = {"busy_clocks": int(m.group(1)), "checksum": int(m.group(2)), "rtl": str(f.relative_to(ROOT))}
base = rows["original (fixture)"]
for r in rows.values():
    r["added_clocks"] = r["busy_clocks"] - base["busy_clocks"]
    r["same_counts_as_original"] = r["checksum"] == base["checksum"]
(HERE / "latency.json").write_text(json.dumps(rows, indent=1) + "\n")
for k, r in rows.items():
    print(f"{k:28s} busy {r['busy_clocks']:3d}  added {r['added_clocks']:+d}  same counts {r['same_counts_as_original']}")
