"""Paired comparison of agent configurations (arms) against a base arm, on the same problems, with repeats.

An arm is a set of collect.py rows. Each run in it is one (CSV file, seed) pair: two dispatches of an arm pool as
long as their seeds differ (the sweep's `seed_offset`). Arms come from `--arm NAME=a.csv,b.csv` (repeatable), or,
with plain CSV arguments, from each row's label plus its agent settings (self-check, lint, turn cap, budget).

Per arm: pass rate per run; pooled pass@1 with a 95% interval from a bootstrap over problems (each problem's runs
kept together, as in table.py); cost, $/problem, $/solved, median wall time and tokens. Cost is provider-reported
only: a row with unreported cost makes the arm's money a lower bound (≥), never an estimate.

Against the base: the paired effect is the mean over common problems of (arm pass rate − base pass rate), where a
problem's pass rate is its passes over its runs in that arm; its 95% interval comes from a paired bootstrap over
problems. Problems are counted as better, worse or the same, and an exact two-sided sign test is run on the better
and worse ones (ties dropped). Arms whose interval includes 0 are listed first, as "no detectable effect".

The Pareto chart is pass rate against $ per problem; an arm is on the frontier if no other arm has at least its pass
rate for at most its cost, and is strictly better on one. `--pareto-csv` and `--pareto-svg` write it (the SVG is
written by this code; no external service).

Usage: python3 tools/ablate.py [--arm NAME=a.csv,b.csv ...] [--base NAME] [--pareto-csv F] [--pareto-svg F]
           [--ids FILE] [csv ...]
"""
import argparse
import csv
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import table  # noqa: E402

BOOT = 2000
DEFAULTS = {"self_check": "1", "lint": "1", "max_turns": "10", "budget_usd": "0.1"}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def settings(r):
    """The agent settings that differ from the M2 defaults, as a short string ("" for the defaults)."""
    out = []
    for k, d in DEFAULTS.items():
        v = str(r.get(k, "")).strip()
        if v and _f(v) != _f(d):
            out.append(f"{k}={v}")
    return " ".join(out)


def load(path):
    """A run CSV's rows. M3h: a row stopped by the Claude plan's limit (stop_reason `rate_limited`) was not run, so it
    is left out (counted on stderr), never scored as a failure; it is rerun and the rerun's row is used instead."""
    with open(path) as f:
        rows = list(csv.DictReader(f))
    # M3i: a `profile_error` row (Claude Code's init event was not the profile asked for) was not run either
    limited = [r for r in rows if r.get("stop_reason") in ("rate_limited", "profile_error")]
    if limited:
        print(f"ablate.py: {path}: {len(limited)} rate-limited or profile-error row(s) left out (not run)",
              file=sys.stderr)
        rows = [r for r in rows if r.get("stop_reason") not in ("rate_limited", "profile_error")]
    for r in rows:
        r["_run"] = f"{os.path.normpath(path)}#seed{r.get('seed') or '1'}"
    return rows


def arms_from(arm_specs, paths):
    """{arm name: rows}. Named arms from --arm; the rest grouped by label + settings."""
    arms = {}
    for spec in arm_specs or []:
        name, _, files = spec.partition("=")
        if not name or not files:
            raise SystemExit(f"--arm wants NAME=a.csv[,b.csv], got {spec!r}")
        arms.setdefault(name, [])
        for p in files.split(","):
            arms[name] += load(p)
    for p in paths or []:
        for r in load(p):
            base = r.get("label") or r.get("requested_model") or r.get("model") or "unknown"
            s = settings(r)
            arms.setdefault(f"{base} {s}".strip() if s else base, []).append(r)
    return arms


def per_problem(rows):
    """{problem id: pass rate over its runs}."""
    acc = {}
    for r in rows:
        acc.setdefault(r["id"], []).append(1.0 if r["pass"] == "1" else 0.0)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def run_rates(rows):
    """{run: pass rate}."""
    acc = {}
    for r in rows:
        acc.setdefault(r["_run"], []).append(1 if r["pass"] == "1" else 0)
    return {k: sum(v) / len(v) for k, v in sorted(acc.items())}


LEVEL = [0.95]  # the paired interval's coverage; --level sets it (M3d: 0.975, Bonferroni over two comparisons)


def bootstrap_mean(values, b=BOOT, seed=0, level=None):
    """Percentile interval (95% unless --level) of the mean of `values`, resampling them with replacement.
    Deterministic."""
    level = level or LEVEL[0]
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(b))
    tail = (1 - level) / 2
    return (means[int(round(tail * b, 9))], means[min(b - 1, int(round((1 - tail) * b, 9)))])


def sign_test(better, worse):
    """Exact two-sided sign test (binomial, p = 1/2) on better/worse counts, ties already dropped."""
    n = better + worse
    if n == 0:
        return 1.0
    k = min(better, worse)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired(arm_rows, base_rows):
    """Paired effect of an arm against the base on the problems both have."""
    a, b = per_problem(arm_rows), per_problem(base_rows)
    common = sorted(set(a) & set(b))
    diffs = [a[p] - b[p] for p in common]
    better = sum(1 for d in diffs if d > 0)
    worse = sum(1 for d in diffs if d < 0)
    lo, hi = bootstrap_mean(diffs)
    # M3j: per-problem rates are thirds, so a bound that is exactly 0 can come out as +/-1e-17; round before the
    # verdict, so a bound of 0 reads as "includes 0" (no detectable effect), as the pre-registered rule says
    lo, hi = round(lo, 9), round(hi, 9)
    return {"problems": len(common), "effect": statistics.mean(diffs) if diffs else 0.0, "lo": lo, "hi": hi,
            "better": better, "worse": worse, "same": len(common) - better - worse,
            "p_sign": sign_test(better, worse),
            # left out of the paired effect (the Arms table still pools over them)
            "arm_only": sorted(set(a) - set(b)), "base_only": sorted(set(b) - set(a))}


def summary(rows):
    s = table.stats(rows)
    lo, hi = table.problem_bootstrap(rows)
    walls = [w for w in (_f(r.get("wall_time_s")) for r in rows) if w is not None]
    return {"rows": s["n"], "passes": s["k"], "rate": s["k"] / s["n"] if s["n"] else 0.0, "lo": lo, "hi": hi,
            "cost": s["cost"], "unreported": s["unreported"], "per_problem": s["per_problem"],
            "per_solved": s["per_solved"], "wall": statistics.median(walls) if walls else None,
            "tokens": s["tokens"], "runs": run_rates(rows)}


def pareto(points, lower=()):
    """points: {name: (cost per problem, pass rate)}. Names on the frontier: not dominated by another arm.
    Arms in `lower` have unreported cost, so their $/problem is only a lower bound: they are never on the frontier
    and never count as dominating another arm (their real cost is not known)."""
    front = set()
    for n, (c, p) in points.items():
        if n in lower:
            continue
        dominated = any(c2 <= c and p2 >= p and (c2 < c or p2 > p)
                        for m, (c2, p2) in points.items() if m != n and m not in lower)
        if not dominated:
            front.add(n)
    return front


def pick_base(arms, base):
    if base:
        if base not in arms:
            raise SystemExit(f"--base {base!r} is not an arm; arms: {', '.join(arms)}")
        return base
    plain = [n for n, rows in arms.items() if rows and not settings(rows[0])]
    if len(plain) == 1:
        return plain[0]
    raise SystemExit("cannot tell which arm is the base; pass --base NAME")


def pct(x):
    return f"{100 * x:.1f}"


def verdict(p):
    if p["lo"] <= 0 <= p["hi"]:
        return "no detectable effect"
    return "worse than base" if p["hi"] < 0 else "better than base"


def report(arms, base):
    res = {n: summary(r) for n, r in arms.items()}
    pairs = {n: paired(arms[n], arms[base]) for n in arms if n != base}
    order = {"no detectable effect": 0, "worse than base": 1, "better than base": 2}
    names = sorted(pairs, key=lambda n: (order[verdict(pairs[n])], pairs[n]["effect"], n))
    lv = f"{100 * LEVEL[0]:g}%"
    out = [f"#### Paired effect against the base (`{base}`)\n",
           "Effect = mean over common problems of (arm pass rate − base pass rate), in points of pass rate. "
           f"{lv} interval: paired bootstrap over problems. Sign test: exact, two-sided, on the problems that "
           "changed. Arms whose interval includes 0 come first.\n",
           f"| Arm | Finding | Effect [{lv}] | Better / worse / same | Sign test p | Problems | Dropped |",
           "|---|---|---|---|---|---|---|"]
    for n in names:
        p = pairs[n]
        out.append(f"| {n} | {verdict(p)} | {100 * p['effect']:+.1f} [{100 * p['lo']:+.1f}, {100 * p['hi']:+.1f}] "
                   f"| {p['better']} / {p['worse']} / {p['same']} | {p['p_sign']:.3g} | {p['problems']} "
                   f"| {len(p['arm_only']) + len(p['base_only'])} |")
    dropped = [(n, pairs[n]) for n in names if pairs[n]["arm_only"] or pairs[n]["base_only"]]
    out += ["", "Problems left out of the paired effect (in only one of the arm and the base; the Arms table "
            "below still pools over them): " + ("none." if not dropped else "")]
    for n, p in dropped:
        short = lambda ids: ", ".join(f"`{i.replace('cvdp_agentic_', '')}`" for i in ids)  # noqa: E731
        out.append(f"- {n}: " + "; ".join(x for x in (
            f"{len(p['arm_only'])} only in the arm ({short(p['arm_only'])})" if p["arm_only"] else "",
            f"{len(p['base_only'])} only in the base ({short(p['base_only'])})" if p["base_only"] else "") if x))
    out += ["", "#### Arms\n",
            "| Arm | Runs: pass rate each | Pooled pass@1 [95% problem bootstrap] | Cost | $/problem | $/solved "
            "| Median wall | Tokens |",
            "|---|---|---|---|---|---|---|---|"]
    for n in [base] + names:
        s = res[n]
        lb = s["unreported"] > 0
        runs = ", ".join(f"{pct(v)}%" for v in s["runs"].values())
        wall = "n/a" if s["wall"] is None else f"{s['wall']:.0f} s"
        cost = table.money(s["cost"], lb) + (f" ({s['unreported']} unreported)" if lb else "")
        out.append(f"| {n}{' (base)' if n == base else ''} | {len(s['runs'])}: {runs} | {s['passes']}/{s['rows']} = "
                   f"{pct(s['rate'])}% [{pct(s['lo'])}, {pct(s['hi'])}] | {cost} | "
                   f"{table.money(s['per_problem'], lb)} | {table.money(s['per_solved'], lb)} | {wall} "
                   f"| {s['tokens']:,} |")
    points = {n: (s["per_problem"] or 0.0, s["rate"]) for n, s in res.items()}
    lower = {n for n, s in res.items() if s["unreported"] > 0}
    front = pareto(points, lower)
    out += ["", "#### Pareto: pass rate against $ per problem\n", "| Arm | $/problem | Pass rate | Frontier |",
            "|---|---|---|---|"]
    for n in sorted(points, key=lambda n: points[n][0]):
        mark = "n/a (cost a lower bound)" if n in lower else ("yes" if n in front else "")
        out.append(f"| {n} | {table.money(points[n][0], n in lower)} | {pct(points[n][1])}% | {mark} |")
    if lower:
        out.append("\n≥: some of the arm's cost was not reported, so its $/problem is a lower bound. It is drawn hollow "
                   "and kept off the frontier.")
    return "\n".join(out) + "\n", res, pairs, points, front


def write_pareto_csv(path, points, front, res):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "usd_per_problem", "pass_rate", "frontier", "cost_lower_bound"])
        for n in sorted(points, key=lambda n: points[n][0]):
            w.writerow([n, round(points[n][0], 6), round(points[n][1], 4), int(n in front),
                        int(res[n]["unreported"] > 0)])


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg(points, front, width=640, height=420, lower=()):
    """A scatter of $ per problem (x) against pass rate (y), with the frontier joined. Plain SVG, no scripts."""
    m = {"l": 64, "r": 24, "t": 24, "b": 48}
    xs = [c for c, _ in points.values()] or [0.0]
    xmax = max(xs) * 1.15 or 0.01
    x = lambda c: m["l"] + (width - m["l"] - m["r"]) * c / xmax  # noqa: E731
    y = lambda p: height - m["b"] - (height - m["t"] - m["b"]) * p  # noqa: E731
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" font-family="sans-serif" font-size="11">',
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
           f'<line x1="{m["l"]}" y1="{y(0)}" x2="{width - m["r"]}" y2="{y(0)}" stroke="#555"/>',
           f'<line x1="{m["l"]}" y1="{y(0)}" x2="{m["l"]}" y2="{y(1)}" stroke="#555"/>']
    for i in range(0, 11, 2):
        p = i / 10
        out.append(f'<text x="{m["l"] - 6}" y="{y(p) + 4:.1f}" text-anchor="end" fill="#333">{i * 10}%</text>')
        out.append(f'<line x1="{m["l"]}" y1="{y(p):.1f}" x2="{width - m["r"]}" y2="{y(p):.1f}" stroke="#eee"/>')
    for i in range(5):
        c = xmax * i / 4
        out.append(f'<text x="{x(c):.1f}" y="{y(0) + 16}" text-anchor="middle" fill="#333">${c:.3f}</text>')
    out.append(f'<text x="{(width + m["l"]) / 2}" y="{height - 10}" text-anchor="middle" fill="#333">'
               f'$ per problem (provider-reported)</text>')
    out.append(f'<text x="14" y="{(height - m["b"]) / 2}" transform="rotate(-90 14 {(height - m["b"]) / 2})" '
               f'text-anchor="middle" fill="#333">pass@1</text>')
    fr = sorted((points[n] for n in front), key=lambda t: t[0])
    if len(fr) > 1:
        path = " ".join(f"{x(c):.1f},{y(p):.1f}" for c, p in fr)
        out.append(f'<polyline points="{path}" fill="none" stroke="#2b6cb0" stroke-width="1.5"/>')
    for n, (c, p) in sorted(points.items()):
        on = n in front
        if n in lower:  # cost is a lower bound: hollow, and its label says so
            out.append(f'<circle cx="{x(c):.1f}" cy="{y(p):.1f}" r="4" fill="#ffffff" stroke="#718096" '
                       f'stroke-width="1.5"/>')
            n = f"{n} (≥${c:.4f}/problem)"
        else:
            out.append(f'<circle cx="{x(c):.1f}" cy="{y(p):.1f}" r="{5 if on else 4}" '
                       f'fill="{"#2b6cb0" if on else "#a0aec0"}"/>')
        right = x(c) > m["l"] + (width - m["l"] - m["r"]) * 0.6  # label to the left of points near the right edge
        out.append(f'<text x="{x(c) + (-7 if right else 7):.1f}" y="{y(p) - 6:.1f}" '
                   f'text-anchor="{"end" if right else "start"}" fill="#1a202c">{_esc(n)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="*")
    ap.add_argument("--arm", action="append", help="NAME=a.csv[,b.csv]")
    ap.add_argument("--base", help="the base arm's name")
    ap.add_argument("--pareto-csv")
    ap.add_argument("--pareto-svg")
    ap.add_argument("--ids", help="a file of problem ids (one per line, # comments): keep only those problems, "
                                  "e.g. tools/m3b_eval_ids.txt for M3b's evaluation set")
    ap.add_argument("--exclude", help="a file of problem ids to leave out (applied after --ids), e.g. "
                                      "tools/benchmark_limited_ids.txt")
    ap.add_argument("--level", type=float, default=0.95, help="coverage of the paired interval (default 0.95)")
    a = ap.parse_args(argv)
    LEVEL[0] = a.level
    arms = arms_from(a.arm, a.csv)
    if a.ids:
        keep = {ln.strip() for ln in open(a.ids) if ln.strip() and not ln.startswith("#")}
        arms = {n: [r for r in rows if r["id"] in keep] for n, rows in arms.items()}
    if a.exclude:
        drop = {ln.strip() for ln in open(a.exclude) if ln.strip() and not ln.startswith("#")}
        arms = {n: [r for r in rows if r["id"] not in drop] for n, rows in arms.items()}
    if len(arms) < 2:
        raise SystemExit("need at least two arms")
    base = pick_base(arms, a.base)
    md, res, _, points, front = report(arms, base)
    if a.pareto_csv:
        write_pareto_csv(a.pareto_csv, points, front, res)
    if a.pareto_svg:
        with open(a.pareto_svg, "w") as f:
            f.write(svg(points, front, lower={n for n, s in res.items() if s["unreported"] > 0}))
    print(md)


if __name__ == "__main__":
    main()
