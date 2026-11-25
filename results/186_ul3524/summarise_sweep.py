#!/usr/bin/env python3
"""Summarise the 186 sweep: read sweep_run_*.log (xsim logs of AMD's testbench) and print min/median/spread
of the per-record latency (clocks of the 644.53125 MHz latency counter, 1.5515 ns as in AMD's testbench) over all runs.
usage: summarise_sweep.py <dir with sweep_run_*.log> <raw|mac>"""
import re, sys, glob, statistics as st
d, mode = sys.argv[1], sys.argv[2]
CLK = 1.5515  # ns, VNC_LATENCY_CLK_PERIOD_NS in AMD's testbench
runs = {}
for f in sorted(glob.glob(d + '/sweep_run_*.log'), key=lambda x: int(re.search(r'run_(\d+)', x).group(1))):
    n = int(re.search(r'run_(\d+)', f).group(1))
    txt = open(f).read()
    if mode == 'raw':
        v = [float(x) for x in re.findall(r'Delta=\s*([-\d.]+) cycles', txt)]
    else:
        v = [float(x) for x in re.findall(r'Latency:\s+([-\d.]+) ticks', txt)]
    runs[n] = v
allv = [x for v in runs.values() for x in v]
print("mode", mode, "runs", len(runs), "records", len(allv))
for n, v in runs.items():
    if v: print("  run %2d: n=%2d min %.2f median %.2f max %.2f clocks" % (n, len(v), min(v), st.median(v), max(v)))
    else: print("  run %2d: no records" % n)
if allv:
    print("ALL: min %.2f median %.2f max %.2f spread %.2f clocks = min %.2f ns, median %.2f ns, max %.2f ns (x %.4f ns/clock)" %
          (min(allv), st.median(allv), max(allv), max(allv) - min(allv), min(allv) * CLK, st.median(allv) * CLK, max(allv) * CLK, CLK))
