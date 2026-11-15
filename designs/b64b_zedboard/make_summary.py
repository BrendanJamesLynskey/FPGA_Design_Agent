#!/usr/bin/env python3
"""make_summary.py: read the committed ZedBoard records (build reports, DDR console logs) into results/64b_zedboard/summary.json,
the single record the design's handover.yaml cites. Run from the repository root; no tool or board needed.
    python3 designs/b64b_zedboard/make_summary.py"""
import json, re, pathlib
R = pathlib.Path("results/64b_zedboard")
def stat(path):
    d = {}
    for l in (R / path).read_text().splitlines():
        m = re.match(r"S (\S+) (\d+) n=(\d+) unit=ns (\S+) (\S+) (\S+) (\S+) (\S+)", l)
        if m: d.setdefault(m[1], {})[int(m[2])] = {"min_ns": float(m[4]), "p50_ns": float(m[5]), "p95_ns": float(m[6]), "max_ns": float(m[7]), "reps": int(m[3])}
    return d
def num(pat, txt): return float(re.search(pat, txt).group(1))
util = (R / "builds/full/utilization.rpt").read_text(); tim = (R / "builds/full/timing.rpt").read_text(); pw = (R / "builds/full/power.rpt").read_text()
wns = re.search(r"WNS\(ns\).*\n.*\n\s+(\S+)\s+\S+\s+\d+\s+\d+\s+(\S+)", tim)
out = {"build": {"lut": int(num(r"\| Slice LUTs\s+\|\s+(\d+)", util)), "ff": int(num(r"\| Slice Registers\s+\|\s+(\d+)", util)),
                 "bram_tile": int(num(r"\| Block RAM Tile\s+\|\s+(\d+)", util)), "dsp": int(num(r"\| DSPs\s+\|\s+(\d+)", util)),
                 "wns_ns": float(wns[1]), "whs_ns": float(wns[2]), "power_w": num(r"Total On-Chip Power \(W\)\s+\|\s+(\S+)", pw),
                 "tj_c": num(r"Junction Temperature \(C\)\s+\|\s+(\S+)", pw)}}
out["build"]["fclk_mhz"] = num(r"clk_fpga_0\s+\{0.000 5.000\}\s+\S+\s+(\S+)", tim)
gp = stat("bringup/gp_latency_run2.log")
out["gp"] = {k: gp[k][0] for k in ("gt_overhead", "gp_read_id", "gp_write_dsb", "gp_read_period_fabric_clk", "ddr_read_l1_hit")}
irq = stat("bringup/irq_latency_caches_on.log"); irq0 = stat("bringup/irq_latency_caches_off.log")
out["irq"] = {"caches_on_busy_loop": irq["irq_busy_loop_caches_on"][1], "caches_off": irq0["irq_busy_loop_caches_off"][0]}
for name, f in (("crc32", "sweeps/crc32_sweep.log"), ("fir16", "sweeps/fir16_sweep.log")):
    s = stat(f); out[name] = {k: {str(b): v for b, v in d.items()} for k, d in s.items()}
be = {}
for f in sorted((R / "bus_errors").glob("e_*.log")):
    m = re.search(r"^E (\S+) ([RW]) (\S+) .* abort_at_barrier=(\d+) abort_late=(\d+) no_abort=(\d+) precise=(\d+).*?(?:DFSR=(\w+)x(\d+))?", f.read_text(), re.M)
    if m:
        dfsr = re.findall(r"DFSR=(\w+)x(\d+)", f.read_text())
        be[f.stem] = {"target": m[1], "access": m[2], "mapping": m[3], "abort_at_barrier": int(m[4]), "abort_late": int(m[5]), "no_abort": int(m[6]),
                      "precise": int(m[7]), "dfsr": dfsr[0][0] if dfsr else None}
out["bus_errors"] = be
(R / "summary.json").write_text(json.dumps(out, indent=1) + "\n")
print("wrote", R / "summary.json", len(be), "bus-error runs")
