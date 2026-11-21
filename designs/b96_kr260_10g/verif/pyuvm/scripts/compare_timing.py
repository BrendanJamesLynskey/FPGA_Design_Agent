#!/usr/bin/env python3
"""The wall-time comparison of brief 123: `compare_timing.py <results dir> > timing_compare.txt`. Reads xsim_timing.tsv (scripts/time_xsim.sh: brief 112's bench in xsim)
and results.tsv (scripts/run_regress.py: this bench in Icarus), same 42-run shape; the build times and the mutant-run estimate are computed from them, and said so."""
import csv
import sys
from pathlib import Path

R = Path(sys.argv[1])
x = {r["item"]: r for r in csv.DictReader(open(R / "xsim_timing.tsv"), delimiter="\t")}
p = {f"{r['test']}_{r['seed']}": r for r in csv.DictReader(open(R / "results.tsv"), delimiter="\t")}
mut = list(csv.DictReader(open(R / "mutants.tsv"), delimiter="\t"))
mutb = list(csv.DictReader(open(R / "mutants_blind.tsv"), delimiter="\t"))
build_x = float(x["build"]["wall_s"])
runs = [k for k in x if k != "build"]
print("seed-1 run of each test: wall seconds and simulated ns (xsim: brief 112's bench; pyuvm: this bench; same test names, random tests draw different streams)")
print(f"{'test':<16}{'xsim s':>8}{'xsim ns':>10}{'pyuvm s':>9}{'pyuvm ns':>10}")
for t in ["t_smoke", "t_lens", "t_gaps", "t_badfcs", "t_xg", "t_line_blocks", "t_hdr", "t_slip", "t_ber", "t_rxreset", "t_offsets", "t_rand", "t_rand_line"]:
    k = f"{t}_1"
    print(f"{t:<16}{float(x[k]['wall_s']):>8.1f}{float(x[k]['sim_ns']):>10.0f}{float(p[k]['wall_s']):>9.1f}{float(p[k]['sim_ns']):>10.0f}")
xw = sum(float(x[k]["wall_s"]) for k in runs)
pw = sum(float(p[k]["wall_s"]) for k in runs)
xn = sum(float(x[k]["sim_ns"]) for k in runs)
pn = sum(float(p[k]["sim_ns"]) for k in runs)
print(f"\nthe {len(runs)}-run regression (11 directed x 2 seeds, 2 random x 10 seeds), simulator wall time summed over the runs, load waits excluded:")
print(f"  xsim   {xw:7.1f} s for {xn / 1e6:.3f} ms simulated; mean {xw / len(runs):.1f} s per run")
print(f"  pyuvm  {pw:7.1f} s for {pn / 1e6:.3f} ms simulated; mean {pw / len(runs):.1f} s per run")


def fit(ys, xs):
    """least squares y = a + b x"""
    n = len(xs); mx, my = sum(xs) / n, sum(ys) / n
    b = sum((a - mx) * (c - my) for a, c in zip(xs, ys)) / sum((a - mx) ** 2 for a in xs)
    return my - b * mx, b


ax, bx = fit([float(x[k]["wall_s"]) for k in runs], [float(x[k]["sim_ns"]) / 6.206 for k in runs])
ap, bp = fit([float(p[k]["wall_s"]) for k in runs], [float(p[k]["sim_ns"]) / 6.206 for k in runs])
print(f"  linear fit of wall time against simulated clocks over the {len(runs)} runs: xsim {ax:.1f} s fixed + {bx * 1000:.2f} ms per clock; pyuvm {ap:.1f} s fixed + {bp * 1000:.2f} ms per clock "
      f"(marginal cost {bp / bx:.0f} times xsim's)")
print(f"build: xsim {build_x:.1f} s (xvlog + xelab, UVM 1.2 package compiled each time); pyuvm {0.1:.1f} s (iverilog; measured by `pyuvm_run.py build`, 0.1 s)")
print(f"regression including one build: xsim {build_x + xw:.0f} s, pyuvm {0.1 + pw:.0f} s")
n_m, n_mb = sum(int(r["runs"]) for r in mut), sum(int(r["runs"]) for r in mutb)
print(f"\nmutant runs (17 bugs, tests in a fixed order until one fails): pyuvm measured {sum(float(r['wall_s']) for r in mut):.0f} s for {n_m} runs; with the hindsight patterns left out (blind) "
      f"{sum(float(r['wall_s']) for r in mutb):.0f} s for {n_mb} runs")
print(f"  xsim, COMPUTED (not run): 17 builds x {build_x:.1f} s + {n_m} runs x {xw / len(runs):.1f} s = {17 * build_x + n_m * xw / len(runs):.0f} s; blind {17 * build_x + n_mb * xw / len(runs):.0f} s")

# the mutant verdicts against brief 112's, mutant by mutant
r112 = Path(__file__).resolve().parents[5] / "results" / "112_uvm_pcs_mac" / "mutants.tsv"
if r112.exists():
    a = {r["id"]: r for r in csv.DictReader(open(r112), delimiter="\t")}
    b = {r["id"]: r for r in mut}
    same_v = sum(a[k]["verdict"] == b[k]["verdict"] for k in a)
    same_t = sum(a[k]["killed_by"] == b[k]["killed_by"] for k in a)
    same_c = sum(set(a[k]["checks_that_fired"].split()) == set(b[k]["checks_that_fired"].split()) for k in a)
    diff = [f"{k} (112: {a[k]['checks_that_fired']}; pyuvm: {b[k]['checks_that_fired']})" for k in a if set(a[k]["checks_that_fired"].split()) != set(b[k]["checks_that_fired"].split())]
    print(f"\nagainst 112's mutants.tsv over {len(a)} mutants: same verdict {same_v}, same killing test and seed {same_t}, same set of checks that fired {same_c}; differences: {'; '.join(diff) or 'none'}")
