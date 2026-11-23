#!/usr/bin/env python3
"""Render the brief 194 result tables (Markdown) from results/b194/*.json. Every number in docs/assurance.md's Results section comes from here.

    python3 -m flow.assurance_report            print the tables
    python3 -m flow.assurance_report --write    also rewrite the section between the markers in docs/assurance.md and results/b194/README.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results" / "b194"
BEGIN, END = "<!-- b194-results:start -->", "<!-- b194-results:end -->"


def load(name: str):
    f = R / name
    return json.loads(f.read_text()) if f.is_file() else None


def pct(a, n):
    return f"{100 * a / n:.0f} %" if n else "n/a"


def fault_table(d) -> str:
    if not d:
        return "_not run_\n"
    tg = {"ram": "one bit of a stored word", "ram2": "two bits of a stored word", "state": "one bit of the state register", "cnt": "one bit of the remaining counter",
          "cnt2": "same bit in two TMR copies", "bus": "one bit of the output register or parity"}
    lines = [f"Seeded, {d['trials']} trials per cell, seed {d['seed']}. Each cell: **masked / corrected / detected / silent / hang** (counts of trials). "
             "`corrected` = output right and a flag raised; `detected` = output wrong or no completion, flag raised; `silent` = wrong output, no flag; `hang` = no completion, no flag.\n"]
    vs = list(d["variants"])
    lines.append("| fault | " + " | ".join(vs) + " |")
    lines.append("|---|" + "---|" * len(vs))
    for t, name in tg.items():
        row = []
        for v in vs:
            r = d["variants"][v]["targets"].get(t)
            row.append("-" if r is None else f"{r['masked']} / {r['corrected']} / {r['detected']} / **{r['silent']}** / {r['hang']}")
        lines.append(f"| {name} | " + " | ".join(row) + " |")
    lines.append("\nVariants: " + "; ".join(f"`{v}` = " + ", ".join(f"{k}={x}" for k, x in d["variants"][v]["params"].items() if x) or "none" for v in vs) + ".\n")
    return "\n".join(lines) + "\n"


def cost_table(c) -> str:
    if not c or not c.get("variants"):
        return "_not run_\n"
    lines = [f"{c['part']}, Vivado {c['vivado']}, out of context, one run per variant. {c['note']}.\n", "| variant | LUT | FF | RAMB36 | RAMB18 | WNS at 5.0 ns | Fmax est. (MHz) | latency (clocks) |", "|---|---|---|---|---|---|---|---|"]
    for n, r in c["variants"].items():
        if "lut" not in r:
            lines.append(f"| {n} | failed: {r.get('error', '')[:80]} |||||||")
            continue
        lines.append(f"| {n} | {r['lut']} | {r['ff']} | {r['bram36']} | {r['bram18']} | {r['wns_route_ns']:+.3f} | {r['fmax_mhz']} | {r['latency_clocks']} |")
    lines += ["", "| structure | variant | LUT | FF | block RAM tiles | Fmax | latency |", "|---|---|---|---|---|---|---|"]
    for k, s in c["structures"].items():
        lines.append(f"| {k} | {s['variant']} | {s['d_lut']:+d} | {s['d_ff']:+d} | {s['d_bram']:+.1f} | {s['fmax_pct']:+.1f} % | {s['d_latency']:+d} |")
    return "\n".join(lines) + "\n"


def mutant_table(m, n) -> str:
    if not m:
        return "_not run_\n"
    cols = [("lint", "lint"), ("directed_seed1", "directed, 1 seed"), ("seed_sweep", f"{m['seeds']} seeds"), ("formal_1x", f"formal depth {m['formal_depth']}"), ("formal_4x", f"formal depth {4 * m['formal_depth']}")]
    lines = ["Seven RTL bugs planted one at a time in the plain design (`designs/b194_assurance/tests/mutants.py`). `yes` = the method reported a failure on the mutant; the unmutated design passes every method.\n",
             "| mutant | " + " | ".join(c[1] for c in cols) + " |", "|---|" + "---|" * len(cols)]
    for mid, r in m["mutants"].items():
        lines.append(f"| {mid}: {r['what']} | " + " | ".join("yes" if r[k]["caught"] else "no" for k, _ in cols) + " |")
    tot = {k: sum(1 for r in m["mutants"].values() if r[k]["caught"]) for k, _ in cols}
    lines.append("| **caught of %d** | " % len(m["mutants"]) + " | ".join(str(tot[k]) for k, _ in cols) + " |")
    if n:
        lines += ["", "Netlist-level faults (Vivado post-synthesis netlist of the control module for `eqy`, of the whole core for the bench):\n", "| planted fault | eqy | functional bench on the netlist |", "|---|---|---|"]
        for p in n.get("planted", []):
            lines.append(f"| {p.get('what') or p['kind']} | {p.get('eqy', '-')} | {'caught' if p.get('bench_caught') is True else 'not caught' if p.get('bench_caught') is False else p.get('bench_caught', '-')} |")
    return "\n".join(lines) + "\n"


def times_table(p) -> str:
    if not p:
        return "_not run_\n"
    lines = ["Wall time of each profile's checks on the development design, summed from the per-method times below (this PC, one run each, not a benchmark; model time and the independent spec bench are not included).\n",
             "| profile | checks | seconds | against standard |", "|---|---|---|---|"]
    base = p["profiles"]["standard"]["seconds"]
    for n, r in p["profiles"].items():
        lines.append(f"| {n} | {', '.join(r['checks'])} | {r['seconds']:.0f} | {r['seconds'] / base:.1f}x |")
    lines += ["", "| method | seconds | source |", "|---|---|---|"]
    for k, v in p["methods"].items():
        lines.append(f"| {k} | {v['s']:.1f} | {v['source']} |")
    return "\n".join(lines) + "\n"


def render() -> str:
    return "\n".join(["### Fault injection (what each structure catches)\n", fault_table(load("faults.json")),
                      "### Area, Fmax and latency of each structure\n", cost_table(load("costs.json")),
                      "### What each verification method catches\n", mutant_table(load("methods_rtl.json"), load("methods_netlist.json")),
                      "### Time per profile\n", times_table(load("profile_times.json"))])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    text = render()
    print(text)
    if a.write:
        doc = ROOT / "docs" / "assurance.md"
        s = doc.read_text()
        if BEGIN in s:
            s = s[:s.index(BEGIN) + len(BEGIN)] + "\n" + text + s[s.index(END):]
            doc.write_text(s)
        (R / "README.md").write_text("# Results of brief 194\n\nGenerated by `python3 -m flow.assurance_report --write` from the JSON files in this folder. Method and caveats: [docs/assurance.md](../../docs/assurance.md).\n\n" + text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
