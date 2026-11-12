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


def sign_p(lo: int, hi: int) -> float:
    """Exact two-sided sign test on the blocks where the arm was lower / higher (ties dropped). Post hoc, see main()."""
    from math import comb
    n, k = lo + hi, min(lo, hi)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0


def frac(r):
    sc = r.get("score") or {}
    return sc["tests_passed"] / sc["tests"] if sc.get("tests") else 0.0


METRICS = {   # name: (getter, stat, unit)
    "tokens": (lambda r: None if r["hard_limit"] else r.get("tokens"), med, ""),
    "cost_usd": (lambda r: None if r["hard_limit"] else r.get("cost_usd"), med, ""),
    "wall_s": (lambda r: 5400.0 if r["hard_limit"] else r["wall_s"], med, ""),
    "tests_passed_fraction": (frac, lambda v: sum(v) / len(v), ""),
    "stage2_visits": (lambda r: r.get("stage2_visits"), med, ""),
}


PRIMARY = {"H1": ("tokens", "cost_usd"), "H9": ("tokens", "cost_usd"), "H2": ("wall_s",)}
RULE_QUOTE = ("Primary metric per arm: H1: tokens per run (and cost). H2: wall time per run and hangs. Safety metric for both: hidden-bench "
              "tests passed as a fraction of the task's tests, and pass count: an arm that lowers it is not adopted whatever it saves." "\n"
              "Adopt rule (stated before the data): adopt an arm as default only if its primary metric improves by at least 30 % in the paired "
              "median with a bootstrap interval that excludes 0, and the tests-passed fraction does not fall (its mean paired difference interval "
              "does not lie below 0) and pass discordant pairs are not worse than A0's by more than one.")


def paired(full, a, m, skip=lambda v: False):
    get, stat, _u = METRICS[m]
    d, base = [], []
    for v in full.values():
        if skip(v):
            continue
        x, y = get(v[a]), get(v["A0"])
        if x is None or y is None:
            continue
        d.append(x - y)
        base.append(y)
    if not d:
        return None
    ci = boot(d, stat)
    b = stat(base)
    return {"n": len(d), "base": b, "diff": stat(d), "rel": 100 * stat(d) / b if b else None, "ci": ci,
            "excl": ci[0] > 0 or ci[1] < 0, "lo": sum(1 for x in d if x < 0), "hi": sum(1 for x in d if x > 0)}


def main() -> None:
    allrows = rows()
    infra = [r for r in allrows if r.get('infra_failure')]
    rs = [r for r in allrows if not r.get('infra_failure')]
    by = {}
    for r in rs:
        by.setdefault((r["task"], r["seed"]), {})[r["arm"]] = r
    full = {k: v for k, v in by.items() if all(a in v for a in ARMS)}
    md = ["# Brief 42 round 1: paired analysis (written by analyze.py)", "",
          "How to read this file: the unit is the block (task, repeat) with all four arms valid. Tokens and cost leave out blocks where either "
          "run was ended by the hard wall limit (no summary, so no provider-reported total), hence n = 10 or 11 there and 12 elsewhere. "
          "Primary rows: tokens and cost for H1 and H9, wall time and hangs for H2 (prereg, Analysis). Intervals with this few blocks are "
          "close to the observed range. Cost and tokens are slightly undercounted: when a malformed provider response is retried, the "
          "usage of the discarded response is not added to the run's total (`OpenRouterClient`), mostly in A0, which had the most retries.", "",
          f"Runs recorded: {len(allrows)}, of which {len(infra)} infrastructure failures (malformed provider response; re-run, not counted: "
          + ", ".join(f"{r['task']} {r['arm']}" for r in infra) + f"). Valid runs: {len(rs)}. Complete blocks (all four arms): {len(full)} of {len(by)} started; "
          "blocks with a missing arm are left out of the paired rows.", ""]
    if not full:
        md.append("No complete block yet.")
        (HERE / "analysis.md").write_text("\n".join(md) + "\n")
        return
    md += ["Per-arm totals over complete blocks:", "", "| Arm | Runs | Hidden-bench passes | Stage-2 gate passes | Hard-limit runs | Median tokens | "
           "Median wall s | Total cost USD | Sim hangs (runs with one) | Mean tests-passed fraction |", "|---|---|---|---|---|---|---|---|---|---|"]
    for a in ARMS:
        rr = [v[a] for v in full.values()]
        tok = [r["tokens"] for r in rr if r.get("tokens") is not None and not r["hard_limit"]]
        md.append(f"| {a} | {len(rr)} | {sum(1 for r in rr if (r.get('score') or {}).get('pass'))} | "
                  f"{sum(1 for r in rr if r.get('stage2_gate_passed') or r.get('stage2_gates_passed'))} | {sum(1 for r in rr if r['hard_limit'])} | "
                  f"{round(med(tok)) if tok else '-'} | {round(med([5400.0 if r['hard_limit'] else r['wall_s'] for r in rr]))} | "
                  f"{round(sum(r.get('cost_usd') or 0 for r in rr), 3)} | {sum(r.get('sim_hangs') or 0 for r in rr)} "
                  f"({sum(1 for r in rr if r.get('sim_hangs'))}) | {round(sum(frac(r) for r in rr) / len(rr), 3)} |")
    md += ["", "Paired differences, arm minus A0 (median for tokens, cost, wall and visits; mean for the tests-passed fraction), "
           "95 % percentile bootstrap over blocks (10,000 resamples, seed 20261111; the pre-registered statistic); n = blocks used. "
           "The last two columns are POST HOC (not pre-registered) and NOT corrected for the 9 arm-by-metric tests run on tokens, cost and "
           "wall time (Bonferroni 0.05 / 9 = 0.0056): the blocks where the arm was lower / higher than A0, and the exact two-sided sign-test p on those counts.", "",
           "| Arm | Metric | n | A0 (median; mean for the fraction) | Difference | Relative to A0 | 95 % interval | Interval excludes 0 | Lower / higher | Sign p (post hoc) |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for a in ARMS[1:]:
        for m in METRICS:
            r = paired(full, a, m)
            if r is None:
                md.append(f"| {a} | {m} | 0 | - | - | - | - | - | - | - |")
                continue
            rel = f"{r['rel']:+.1f} %" if m in ("tokens", "cost_usd", "wall_s") and r["rel"] is not None else "-"
            if m == "tests_passed_fraction":
                r["base"] = sum(frac(v["A0"]) for v in full.values()) / len(full)
            sp = f"{sign_p(r['lo'], r['hi']):.3f}" if m in ("tokens", "cost_usd", "wall_s") else "-"
            md.append(f"| {a} | {m} | {r['n']} | {round(r['base'], 3)} | {round(r['diff'], 3)} | {rel} | [{round(r['ci'][0], 3)}, {round(r['ci'][1], 3)}] | "
                      f"{'yes' if r['excl'] else 'no'} | {r['lo']} / {r['hi']} | {sp} |")
    md += ["", "Sensitivity (censored blocks): wall time with the blocks that contain a run ended by the hard 5,400 s limit left out (those runs "
           "count 5,400 s in the table above, a floor on their true time):", "",
           "| Arm | n | Difference s | 95 % interval s | Interval excludes 0 | Lower / higher |", "|---|---|---|---|---|---|"]
    for a in ARMS[1:]:
        r = paired(full, a, "wall_s", skip=lambda v: any(x["hard_limit"] for x in v.values()))
        md.append(f"| {a} | {r['n']} | {round(r['diff'], 1)} | [{round(r['ci'][0], 1)}, {round(r['ci'][1], 1)}] | {'yes' if r['excl'] else 'no'} | {r['lo']} / {r['hi']} |")
    md += ["", "Discordant blocks for pass and for stage-2 gates (only the arm passed / only A0 passed):", "",
           "| Arm | Hidden bench: arm only / A0 only | Stage-2 gates: arm only / A0 only |", "|---|---|---|"]
    disc_pass, disc_fraction = {}, {}
    for a in ARMS[1:]:
        def disc(f):
            return (sum(1 for v in full.values() if f(v[a]) and not f(v["A0"])), sum(1 for v in full.values() if f(v["A0"]) and not f(v[a])))
        p = disc(lambda r: (r.get("score") or {}).get("pass"))
        g = disc(lambda r: r.get("stage2_gates_passed"))
        disc_pass[a] = p
        md.append(f"| {a} | {p[0]} / {p[1]} | {g[0]} / {g[1]} |")
    md += ["", "## The pre-registered adopt rule, word for word, and its two readings", "", "> " + RULE_QUOTE.replace("\n", "\n> "), "",
           "The wording \"tokens per run (and cost)\" was not fixed in advance as one reading, so the rule is ambiguous for H1 and H9. Both "
           "readings are reported; the verdict is not chosen after the fact. Reading T: tokens alone, or tokens and cost together (both must "
           "pass). Reading C: tokens or cost (either passes). A metric passes when its paired median improves by at least 30 % of A0's "
           "median and its bootstrap interval excludes 0; the safety conditions are checked separately. H2's primary metric is wall time "
           "(and hangs).", "",
           "| Arm | Tokens | Cost | Wall time | Safety: fraction interval not below 0 | Safety: pass discordants not worse by more than 1 | Meets rule, reading T | Meets rule, reading C |",
           "|---|---|---|---|---|---|---|---|"]
    for a in ARMS[1:]:
        def ok(m):
            r = paired(full, a, m)
            return r is not None and r["excl"] and r["diff"] < 0 and r["rel"] is not None and r["rel"] <= -30, r
        tk, ck, wk = ok("tokens"), ok("cost_usd"), ok("wall_s")
        fr = paired(full, a, "tests_passed_fraction")
        safe_fr = fr["ci"][1] >= 0
        safe_pass = disc_pass[a][1] - disc_pass[a][0] <= 1
        def cell(k):
            r = k[1]
            return f"{'pass' if k[0] else 'fail'} ({r['rel']:+.1f} %, interval {'excludes' if r['excl'] else 'includes'} 0)"
        if a == "H2":
            t_read = c_read = wk[0] and safe_fr and safe_pass
        else:
            t_read = tk[0] and ck[0] and safe_fr and safe_pass
            c_read = (tk[0] or ck[0]) and safe_fr and safe_pass
        md.append(f"| {a} | {cell(tk)} | {cell(ck)} | {cell(wk)} | {'yes' if safe_fr else 'no'} | {'yes' if safe_pass else 'no'} | "
                  f"{'yes' if t_read else 'no'} | {'yes' if c_read else 'no'} |")
    md += ["", "Sim hangs are counts (table of per-arm totals above); the median difference of a count that is 0 in almost every block carries no information. "
           "With this few blocks only a very large effect can be told from noise; an interval that includes 0 is a null."]
    (HERE / "analysis.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
