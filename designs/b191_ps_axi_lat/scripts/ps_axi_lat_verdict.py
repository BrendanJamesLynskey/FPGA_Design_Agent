#!/usr/bin/env python3
"""Judge a board session of ps_axi_lat (brief 191, board row B-R8) against the pre-registration in docs/ps_axi_lat.md.

    python3 -I scripts/ps_axi_lat_verdict.py <results dir>        # reads result_<port>_run<k>.json, writes record.json and summary.md there

Validity criteria (pass/fail): every result file parses; the ID and the build stamp matched (the program refuses otherwise); `integrity_mismatches` and `bad_accesses` are 0 in every run;
every figure has n >= 200000 observations per run, 5 runs per file, 3 files per port; operating conditions were read before and after (files present). The values themselves have no pass or fail
(no prior measurement of this system exists): the record gives, per port and figure, the median of the run medians and the range of the run medians (the spread over runs), and the p99 and p99.9
of the pooled run percentiles when the sample is large enough (>= 100 observations beyond the percentile: p99 from 10,000, p99.9 from 100,000), and then reports the three pre-registered relations
H1 to H3 as confirmed or not confirmed."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

FIGURES = ("read_cpu", "read_fab", "write_cpu", "rw_cpu", "write_fab", "write_burst")


def load(d: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for f in sorted(d.glob("result_*_run*.json")):
        port = f.name.split("_")[1]
        out.setdefault(port, []).append(json.loads(f.read_text()))
    return out


def summarise(files: list[dict]) -> dict:
    res = {}
    for fig in FIGURES:
        runs = [r[fig] for f in files for r in f["runs"]]
        row = {"runs": len(runs), "n_per_run": min(r["n"] for r in runs),
               "median_of_run_medians_ns": statistics.median(r["p50_ns"] for r in runs),
               "run_median_range_ns": [min(r["p50_ns"] for r in runs), max(r["p50_ns"] for r in runs)],
               "min_ns": min(r["min_ns"] for r in runs), "max_ns": max(r["max_ns"] for r in runs)}
        if all("p99_ns" in r for r in runs):
            row["p99_ns_median_of_runs"] = statistics.median(r["p99_ns"] for r in runs)
            row["p99_ns_range"] = [min(r["p99_ns"] for r in runs), max(r["p99_ns"] for r in runs)]
        if all("p999_ns" in r for r in runs):
            row["p999_ns_median_of_runs"] = statistics.median(r["p999_ns"] for r in runs)
        res[fig] = row
    return res


def main(argv: list[str]) -> int:
    d = Path(argv[1])
    by_port = load(d)
    problems = []
    if set(by_port) != {"fpd", "lpd"}:
        problems.append(f"expected result files for fpd and lpd, found {sorted(by_port)}")
    for port, files in by_port.items():
        if len(files) != 3:
            problems.append(f"{port}: {len(files)} result files, 3 expected")
        for f in files:
            if f.get("integrity_mismatches") != 0 or f.get("bad_accesses") != 0:
                problems.append(f"{port}: integrity or bad-access count not 0")
            if len(f["runs"]) != 5 or any(r[fig]["n"] < 200000 for r in f["runs"] for fig in FIGURES):
                problems.append(f"{port}: fewer than 5 runs or fewer than 200000 observations per figure")
    for need in ("conditions_before.txt", "conditions_after.txt"):
        if not (d / need).is_file():
            problems.append(f"missing {need} (operating conditions are evidence)")
    rec = {"brief": 191, "row": "B-R8", "validity_problems": problems, "valid": not problems, "ports": {p: summarise(fs) for p, fs in by_port.items()},
           "timer_tick_ns": {p: fs[0]["timer_tick_ns"] for p, fs in by_port.items()}, "fabric_clock_hz": {p: fs[0]["clk_hz"] for p, fs in by_port.items()}, "build": {p: fs[0]["build"] for p, fs in by_port.items()}}
    if not problems:
        f, l = rec["ports"]["fpd"], rec["ports"]["lpd"]
        rec["relations"] = {
            "H1_fpd_read_not_slower_than_lpd": f["read_cpu"]["median_of_run_medians_ns"] <= l["read_cpu"]["median_of_run_medians_ns"],
            "H2_write_with_barrier_not_faster_than_read": f["write_cpu"]["median_of_run_medians_ns"] >= f["read_cpu"]["median_of_run_medians_ns"],
            "H3_burst_writes_faster_than_barriered_writes": f["write_burst"]["median_of_run_medians_ns"] < f["write_fab"]["median_of_run_medians_ns"],
        }
    (d / "record.json").write_text(json.dumps(rec, indent=2) + "\n")
    lines = ["| port | figure | median of run medians (ns) | run medians range (ns) | p99 (ns) |", "|---|---|---|---|---|"]
    for p, figs in rec["ports"].items():
        for fig, r in figs.items():
            lines.append(f"| {p} | {fig} | {r['median_of_run_medians_ns']:.1f} | {r['run_median_range_ns'][0]:.1f} to {r['run_median_range_ns'][1]:.1f} | {r.get('p99_ns_median_of_runs', '')} |")
    (d / "summary.md").write_text("\n".join(lines) + "\n\n" + ("valid" if rec["valid"] else "NOT VALID: " + "; ".join(problems)) + "\n")
    print(json.dumps({"valid": rec["valid"], "problems": problems, "relations": rec.get("relations")}, indent=1))
    return 0 if rec["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
