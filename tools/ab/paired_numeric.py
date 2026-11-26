"""Brief 213: a paired comparison of a NUMERIC column between two arms (the binary-to-graded mode 226 asked for; tools/ab/ablate.py is binary only).

Pairs are (design, seed): run k of design d in the treatment arm against run k of design d in the control arm (the replicates are exchangeable, so the pairing
only removes the design effect). Reports the pair differences, their mean, a percentile bootstrap interval over the pairs (resampling pairs, 2000
draws, seed 0), the per-design mean difference, and an exact two-sided sign test on better/worse pairs (ties dropped). "Lower is better" is the default
(visits, cost, wall time); ``--higher-better`` flips the words. Rows whose stop_reason is rate_limited, slot_refused or no_record are not runs and are left out.

  python3 tools/ab/paired_numeric.py runs.csv --base control --arm treatment --col stage2_visits [--col cost_usd ...]
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ablate  # noqa: E402  (bootstrap_mean, sign_test: copied from CVDP_RTL_Agent/tools, MIT)

NOT_RUN = ("rate_limited", "slot_refused", "profile_error", "no_record")


def pairs(rows: list[dict], base: str, arm: str, col: str) -> list[tuple[str, str, float, float]]:
    def val(r):
        try:
            return float(r[col])
        except (KeyError, TypeError, ValueError):
            return None
    by = {}
    for r in rows:
        if r.get("stop_reason") in NOT_RUN or val(r) is None:
            continue
        by.setdefault((r["id"], r["seed"]), {})[r["label"]] = val(r)
    return [(d, s, v[base], v[arm]) for (d, s), v in sorted(by.items()) if base in v and arm in v]


def report(rows: list[dict], base: str, arm: str, col: str, lower_better: bool = True) -> str:
    ps = pairs(rows, base, arm, col)
    if not ps:
        return f"{col}: no complete pairs"
    diffs = [a - b for _, _, b, a in ps]
    lo, hi = ablate.bootstrap_mean(diffs)
    better = sum(1 for x in diffs if (x < 0 if lower_better else x > 0))
    worse = sum(1 for x in diffs if (x > 0 if lower_better else x < 0))
    per = {}
    for (d, _, b, a) in ps:
        per.setdefault(d, []).append(a - b)
    mb, ma = statistics.mean(b for _, _, b, _ in ps), statistics.mean(a for _, _, _, a in ps)
    sd = statistics.pstdev(diffs) if len(diffs) > 1 else 0.0
    verdict = "no detectable effect" if lo <= 0 <= hi else ("treatment better" if (hi < 0) == lower_better else "treatment worse")
    return (f"{col}: control mean {mb:.2f}, treatment mean {ma:.2f} (n = {len(ps)} pairs); mean difference {statistics.mean(diffs):+.2f} "
            f"(95% bootstrap interval {lo:+.2f} to {hi:+.2f}, SD of differences {sd:.2f}); {better} better, {worse} worse, "
            f"{len(diffs) - better - worse} equal, sign test p = {ablate.sign_test(better, worse):.2f}; {verdict}; per design "
            + ", ".join(f"{d} {statistics.mean(v):+.2f}" for d, v in sorted(per.items())))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--base", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--col", action="append", required=True)
    ap.add_argument("--higher-better", action="store_true")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.csv)))
    for c in a.col:
        print(report(rows, a.base, a.arm, c, not a.higher_better))


if __name__ == "__main__":
    main()
