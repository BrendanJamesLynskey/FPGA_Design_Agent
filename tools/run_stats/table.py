"""Results table from one or more collect.py CSVs: pass@1 with a Wilson 95% interval, $/problem, $/solved problem
and median wall time, by category and for the AMBA slice, per model. Markdown on stdout.

Rows are grouped by `label` (the model and its reasoning setting, e.g. "x/y (reasoning off)") when the CSV has
one, else by the requested model.

With --seeds, the rows are repeats of the same problems (the `seed` column), and a table across seeds comes first:
mean pass@1 over seeds with its min-max range, pooled pass@1 with a 95% interval from a bootstrap over problems
(each problem's seeds resampled together, since repeats of one problem are not independent), and the cost per
solved problem pooled across seeds. The per-slice tables after it are pooled over seeds, and their Wilson
intervals treat every problem-seed row as independent, so they overstate the precision.

Usage: python3 tools/table.py [--seeds] results.csv [more.csv ...]
"""
import csv
import math
import random
import statistics
import sys

CID_NAMES = {"cid003": "spec to RTL", "cid004": "RTL modification", "cid005": "spec to RTL, module reuse",
             "cid016": "bug fixing"}


def wilson(k, n, z=1.959964):
    """Wilson score interval for k successes in n trials."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def unreported(r):
    """A row whose cost is not fully known: no reported cost, or some calls without one."""
    return _f(r["cost_usd"]) is None or int(_f(r.get("cost_unreported_calls")) or 0) > 0


def stats(rows):
    n = len(rows)
    k = sum(1 for r in rows if r["pass"] == "1")
    total = sum(_f(r["cost_usd"]) or 0.0 for r in rows)
    walls = [w for w in (_f(r["wall_time_s"]) if _f(r["wall_time_s"]) is not None else _f(r.get("harness_agent_s"))
                         for r in rows) if w is not None]
    lo, hi = wilson(k, n)
    return {
        "n": n, "k": k, "lo": lo, "hi": hi,
        "cost": total, "unreported": sum(1 for r in rows if unreported(r)),
        "per_problem": total / n if n else None,
        "per_solved": total / k if k else None,
        "wall": statistics.median(walls) if walls else None,
        "tokens": sum(int(r["prompt_tokens"] or 0) + int(r["completion_tokens"] or 0) for r in rows),
    }


def money(x, lower_bound=False):
    """A lower bound is shown as ≥$x: some cost in the slice was not reported, and none is ever estimated."""
    return "n/a" if x is None else ("≥" if lower_bound else "") + f"${x:.4f}"


def line(label, s):
    p = f"{s['k']}/{s['n']} = {100 * s['k'] / s['n']:.1f}% [{100 * s['lo']:.1f}, {100 * s['hi']:.1f}]" if s["n"] \
        else "0/0"
    lb = s["unreported"] > 0
    cost = money(s["cost"], lb) + (f" ({s['unreported']} unreported)" if lb else "")
    wall = "n/a" if s["wall"] is None else f"{s['wall']:.0f} s"
    return (f"| {label} | {p} | {cost} | {money(s['per_problem'], lb)} | {money(s['per_solved'], lb)} | {wall} "
            f"| {s['tokens']:,} |")


def group_key(rows):
    if rows and rows[0].get("label"):
        return "label"
    return "requested_model" if rows and "requested_model" in rows[0] else "model"


def table(rows):
    out = []
    key = group_key(rows)
    models = sorted({r[key] for r in rows})
    for m in models:
        mr = [r for r in rows if r[key] == m]
        out.append(f"#### {m}\n")
        out.append("| Slice | pass@1 [Wilson 95%] | Cost | $/problem | $/solved | Median wall | Tokens |")
        out.append("|---|---|---|---|---|---|---|")
        for cid in sorted({r["cid"] for r in mr}):
            out.append(line(f"{cid} {CID_NAMES.get(cid, '')}".strip(), stats([r for r in mr if r["cid"] == cid])))
        amba = [r for r in mr if r["amba"] == "1"]
        if amba:
            out.append(line("AMBA slice", stats(amba)))
        out.append(line("**All**", stats(mr)))
        stops = {}
        for r in mr:
            stops[r["stop_reason"]] = stops.get(r["stop_reason"], 0) + 1
        out.append("\nStop reasons: " + ", ".join(f"{k} {v}" for k, v in sorted(stops.items())))
        if mr and "empty_replies" in mr[0]:
            tot = {c: sum(int(_f(r.get(c)) or 0) for r in mr)
                   for c in ("empty_replies", "empty_retries", "reflect_parse_retries")}
            rt = sum(int(_f(r.get("reasoning_tokens")) or 0) for r in mr)
            out.append(f"\nEmpty replies: {tot['empty_replies']} (retried {tot['empty_retries']}); "
                       f"reflect parse retries: {tot['reflect_parse_retries']}; reasoning tokens (reported): {rt:,}")
        out.append("")
    return "\n".join(out)


def problem_bootstrap(rows, b=2000, seed=0):
    """95% interval for pooled pass@1, resampling problems (each with all its seeds) with replacement."""
    by_problem = {}
    for r in rows:
        by_problem.setdefault(r["id"], []).append(1.0 if r["pass"] == "1" else 0.0)
    means = [sum(v) / len(v) for v in by_problem.values()]
    if not means:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(means)
    stats_ = sorted(sum(rng.choice(means) for _ in range(n)) / n for _ in range(b))
    return (stats_[int(0.025 * b)], stats_[min(b - 1, int(0.975 * b))])


def seeds_table(rows):
    """Across seeds, per model: mean pass@1 over seeds [min-max], pooled pass@1 [95% problem bootstrap], pooled
    cost and $/solved. A seed's pass@1 is its passes over its rows (problems)."""
    key = group_key(rows)
    out = ["#### Across seeds\n",
           "| Model | Seeds | Problems per seed | Mean pass@1 [min–max] | Pooled pass@1 [95% problem bootstrap] "
           "| Cost, all seeds | $/solved, pooled |",
           "|---|---|---|---|---|---|---|"]
    for m in sorted({r[key] for r in rows}):
        mr = [r for r in rows if r[key] == m]
        by_seed = {}
        for r in mr:
            by_seed.setdefault(r.get("seed", ""), []).append(r)
        rates = [stats(v)["k"] / stats(v)["n"] for v in by_seed.values() if v]
        sizes = sorted({len(v) for v in by_seed.values()})
        s = stats(mr)
        lo, hi = problem_bootstrap(mr)
        lb = s["unreported"] > 0
        mean = f"{100 * statistics.mean(rates):.1f}% [{100 * min(rates):.1f}–{100 * max(rates):.1f}]"
        pooled = f"{s['k']}/{s['n']} = {100 * s['k'] / s['n']:.1f}% [{100 * lo:.1f}, {100 * hi:.1f}]"
        cost = money(s["cost"], lb) + (f" ({s['unreported']} unreported)" if lb else "")
        out.append(f"| {m} | {len(by_seed)} | {'/'.join(map(str, sizes))} | {mean} | {pooled} | {cost} "
                   f"| {money(s['per_solved'], lb)} |")
    return "\n".join(out) + "\n"


def main(argv):
    seeds = "--seeds" in argv
    rows = []
    for p in [a for a in argv if a != "--seeds"]:
        with open(p) as f:
            rows += list(csv.DictReader(f))
    if seeds:
        print(seeds_table(rows))
    print(table(rows))


if __name__ == "__main__":
    main(sys.argv[1:])
