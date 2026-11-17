"""Summarise the block-internal path delays of stamp.tcl runs (brief 100, capability 1): for each run, how far each copy's delays are from
copy 0's, endpoint by endpoint (Vivado's data-path delay, in ps), and the worst delay in each copy. Usage:
  analyse_blocks.py <out.json> <label>=<blocks.csv> [<label>=<blocks.csv> ...]
Pure Python; no Vivado, no RapidWright. The delays are Vivado's (report_timing), so the comparison is Vivado's, not an estimate."""
import csv
import json
import sys
from collections import defaultdict
from statistics import mean


def load(path):
    d = defaultdict(dict)
    for r in csv.DictReader(open(path)):
        d[int(r["copy"])][r["endpoint"]] = float(r["data_path_delay_ns"])
    return d


out = {}
for arg in sys.argv[2:]:
    label, path = arg.split("=", 1)
    d = load(path)
    base = d[0]
    run = {"endpoints_copy0": len(base), "copies": {}}
    for c in sorted(d):
        common = sorted(set(base) & set(d[c]))
        diffs = [round((d[c][e] - base[e]) * 1000) for e in common]
        run["copies"][c] = {
            "endpoints": len(d[c]), "common_with_copy0": len(common),
            "worst_delay_ns": max(d[c].values()),
            "mean_abs_diff_ps": round(mean(abs(x) for x in diffs), 1) if diffs else None,
            "max_abs_diff_ps": max((abs(x) for x in diffs), default=None),
            "endpoints_identical": sum(1 for x in diffs if x == 0),
        }
    out[label] = run
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(json.dumps(out, indent=1))
