#!/usr/bin/env python3
"""Paired analysis of runs.jsonl as pre-registered (prereg.md, Analysis): writes analysis.md.

Unit = block (task, seed) with all four arms recorded. Per metric, arm minus A0; percentile bootstrap (10,000 resamples of
blocks, seed 20261111) of the median (tokens, cost, wall) or the mean (tests-passed fraction). Censored runs (hard limit) count
5,400 s of wall and are left out of the token and cost comparisons.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ["A0", "H1", "H2", "H9"]


def rows() -> list[dict]:
    f = HERE / "runs.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []


def med(v):
    v = sorted(v)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def boot(diffs, stat, n=10000, seed=20261111):
    if not diffs:
        return None
    rng = random.Random(seed)
    s = sorted(stat([rng.choice(diffs) for _ in diffs]) for _ in range(n))
    return s[int(0.025 * n)], s[int(0.975 * n) - 1]


def frac(r):
    sc = r.get("score") or {}
    return sc["tests_passed"] / sc["tests"] if sc.get("tests") else 0.0


METRICS = {   # name: (getter, stat, unit)
    "tokens": (lambda r: None if r["hard_limit"] else r.get("tokens"), med, ""),
    "cost_usd": (lambda r: None if r["hard_limit"] else r.get("cost_usd"), med, ""),
    "wall_s": (lambda r: 5400.0 if r["hard_limit"] else r["wall_s"], med, ""),
    "tests_passed_fraction": (frac, lambda v: sum(v) / len(v), ""),
    "sim_hangs": (lambda r: r.get("sim_hangs"), med, ""),
    "stage2_visits": (lambda r: r.get("stage2_visits"), med, ""),
}


def main() -> None:
    rs = rows()
    by = {}
    for r in rs:
        by.setdefault((r["task"], r["seed"]), {})[r["arm"]] = r
    full = {k: v for k, v in by.items() if all(a in v for a in ARMS)}
    md = ["# Brief 42 round 1: paired analysis (written by analyze.py)", "",
          f"Runs recorded: {len(rs)}. Complete blocks (all four arms): {len(full)} of {len(by)} started; "
          "blocks with a missing arm are left out of the paired rows.", ""]
    if not full:
        md.append("No complete block yet.")
        (HERE / "analysis.md").write_text("\n".join(md) + "\n")
        return
    md += ["Per-arm totals over complete blocks:", "", "| Arm | Runs | Hidden-bench passes | Stage-2 gate passes | Hard-limit runs | Median tokens | "
           "Median wall s | Total cost USD | Hangs | Mean tests-passed fraction |", "|---|---|---|---|---|---|---|---|---|---|"]
    for a in ARMS:
        rr = [v[a] for v in full.values()]
        tok = [r["tokens"] for r in rr if r.get("tokens") is not None and not r["hard_limit"]]
        md.append(f"| {a} | {len(rr)} | {sum(1 for r in rr if (r.get('score') or {}).get('pass'))} | "
                  f"{sum(1 for r in rr if r.get('stage2_gates_passed'))} | {sum(1 for r in rr if r['hard_limit'])} | "
                  f"{round(med(tok)) if tok else '-'} | {round(med([5400.0 if r['hard_limit'] else r['wall_s'] for r in rr]))} | "
                  f"{round(sum(r.get('cost_usd') or 0 for r in rr), 3)} | {sum(r.get('sim_hangs') or 0 for r in rr)} | "
                  f"{round(sum(frac(r) for r in rr) / len(rr), 3)} |")
    md += ["", "Paired differences, arm minus A0 (median for tokens, cost, wall, hangs, visits; mean for the tests-passed fraction), "
           "95 % percentile bootstrap over blocks; n = blocks used.", "",
           "| Arm | Metric | n | Median A0 | Difference | 95 % interval | Interval excludes 0 |", "|---|---|---|---|---|---|---|"]
    for a in ARMS[1:]:
        for m, (get, stat, _u) in METRICS.items():
            d, base = [], []
            for v in full.values():
                x, y = get(v[a]), get(v["A0"])
                if x is None or y is None:
                    continue
                d.append(x - y)
                base.append(y)
            if not d:
                md.append(f"| {a} | {m} | 0 | - | - | - | - |")
                continue
            ci = boot(d, stat)
            point = stat(d)
            md.append(f"| {a} | {m} | {len(d)} | {round(med(base), 3)} | {round(point, 3)} | [{round(ci[0], 3)}, {round(ci[1], 3)}] | "
                      f"{'yes' if ci[0] > 0 or ci[1] < 0 else 'no'} |")
    md += ["", "Discordant blocks for pass and for stage-2 gates (only the arm passed / only A0 passed):", "",
           "| Arm | Hidden bench: arm only / A0 only | Stage-2 gates: arm only / A0 only |", "|---|---|---|"]
    for a in ARMS[1:]:
        def disc(f):
            return (sum(1 for v in full.values() if f(v[a]) and not f(v["A0"])), sum(1 for v in full.values() if f(v["A0"]) and not f(v[a])))
        p = disc(lambda r: (r.get("score") or {}).get("pass"))
        g = disc(lambda r: r.get("stage2_gates_passed"))
        md.append(f"| {a} | {p[0]} / {p[1]} | {g[0]} / {g[1]} |")
    md += ["", "With this few blocks only a very large effect can be told from noise; an interval that includes 0 is a null."]
    (HERE / "analysis.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
