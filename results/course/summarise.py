"""Per-task summary of the course run records (brief 08a): pass counts, pass@1 / pass@k, escapes, cost and wall.

    python results/course/summarise.py [--split dev|held-out] [results/course]

Pass means the hidden bench passed (hidden_pass), whatever the agent's own gates did; the outcome columns show how
the run got there.  pass@1 is the mean over runs of the per-run pass (k of n); pass@k is 1 when any of the n runs
passed.  Runs with an unknown hidden verdict are listed but not counted.
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

OUTCOMES = ("pass", "caught_and_repaired", "escape", "internal_stop_hidden_pass", "fail", "unknown")


def load(course_dir: Path) -> list:
    return [json.loads(p.read_text()) for p in sorted(course_dir.glob("*/run_*.json"))]


def _nums(vals):
    return [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _mean(vals):
    nums = _nums(vals)
    return (statistics.fmean(nums), len(nums)) if nums else (None, 0)


def _fmt(v, nd=2):
    return "n/a" if v is None else f"{v:.{nd}f}"


def summarise(runs: list, split: str | None = None) -> str:
    if split:
        runs = [r for r in runs if r.get("split") == split]
    by_task = collections.defaultdict(list)
    for r in runs:
        by_task[r["task"]].append(r)
    out = []
    head = f"{'task':<26}{'split':<9}{'k of n':<8}{'pass@1':<8}{'pass@k':<8}  outcomes"
    out += [head, "-" * len(head)]
    levels = collections.Counter()
    outcomes = collections.Counter()
    tot_k = tot_n = 0
    for task in sorted(by_task):
        rs = by_task[task]
        scored = [r for r in rs if r.get("hidden_pass") in (True, False)]
        k = sum(1 for r in scored if r["hidden_pass"])
        n = len(scored)
        tot_k, tot_n = tot_k + k, tot_n + n
        oc = collections.Counter(r.get("outcome", "unknown") for r in rs)
        outcomes.update(oc)
        for r in rs:
            if r.get("outcome") == "escape":
                levels[r.get("escape_level") or "unclassified"] += 1
        p1 = f"{k / n:.2f}" if n else "n/a"
        pk = ("1" if k else "0") if n else "n/a"
        ocs = ", ".join(f"{o}={oc[o]}" for o in OUTCOMES if oc[o])
        out.append(f"{task:<26}{rs[0].get('split', '?'):<9}{f'{k} of {n}':<8}{p1:<8}{pk:<8}  {ocs}")
    out.append("")
    out.append(f"runs {len(runs)}, scored {tot_n}, hidden pass {tot_k}" + (f" ({tot_k / tot_n:.2f})" if tot_n else ""))
    out.append("outcomes: " + ", ".join(f"{o}={outcomes[o]}" for o in OUTCOMES if outcomes[o]))
    out.append("escapes by level: " + (", ".join(f"{lv}={n}" for lv, n in sorted(levels.items())) or "none"))
    cost, nc = _mean([r.get("plan_cost_estimate_usd") for r in runs])
    wall, nw = _mean([r.get("wall_h_total") for r in runs])
    toks, nt = _mean([r.get("tokens") for r in runs])
    sim, ns = _mean([r["tool_runs"].get("simulate_mutate_build") for r in runs if isinstance(r.get("tool_runs"), dict)])
    out.append(f"mean plan-cost estimate USD {_fmt(cost)} ({nc} runs with a value), mean wall h {_fmt(wall)} ({nw}), "
               f"mean tokens {_fmt(toks, 0)} ({nt}), mean simulate+mutate+build calls {_fmt(sim, 1)} ({ns})")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("course_dir", nargs="?", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--split", choices=("dev", "held-out"))
    a = ap.parse_args(argv)
    print(summarise(load(Path(a.course_dir)), a.split))
    return 0


if __name__ == "__main__":
    sys.exit(main())
