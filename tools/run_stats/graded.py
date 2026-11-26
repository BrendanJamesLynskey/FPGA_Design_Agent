"""Paired comparison of a numeric (graded) outcome between two arms, on the same items, with repeats (brief 218).

``ablate.py`` and ``table.py`` (copied from the CVDP project, see NOTICE.md) compare a pass rate. A run of this agent is better described by a graded
outcome (how far it got, how many holes it closed per million tokens, how many requirement rows it evidenced, what it cost), which carries far less
variance than a 0/1 pass at the same number of items (reports/226 section 4). This module reads rows with an item id, a seed, an arm label and any
numeric columns, and reports for each column the paired effect of an arm against the base arm: the mean over the common items of
(arm mean over its runs of the item - base mean over its runs), its 95 % interval from a paired bootstrap over items (``ablate.bootstrap_mean``), the
items better, worse and the same, and the exact sign test (``ablate.sign_test``). The interval includes zero: "no detectable effect".

Run records to rows: ``rows_from_runs`` reads the ``run_record.json`` of a run (the pilot's format) or a dict of the same keys.

    python3 tools/run_stats/graded.py --base A0 --col holes_closed_per_mtok --col tokens rows.csv

The CSV has the columns ``id, seed, arm`` and the numeric columns; ``stop_reason`` of ``rate_limited``, ``plan_limit``, ``slot_refused`` or
``profile_error`` marks a run that was not run: it is left out and counted on stderr, never scored as a failure (the run is re-run and its row is
used instead).
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ablate  # noqa: E402

NOT_RUN = ("rate_limited", "plan_limit", "slot_refused", "profile_error")


def load(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    gone = [r for r in rows if r.get("stop_reason") in NOT_RUN]
    if gone:
        print(f"graded.py: {path}: {len(gone)} row(s) not run (plan limit, rate limit, slot refused) left out", file=sys.stderr)
    return [r for r in rows if r.get("stop_reason") not in NOT_RUN]


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def per_item(rows, col):
    """{item id: mean of ``col`` over its runs}; a run with no value for the column is left out."""
    acc = {}
    for r in rows:
        v = _num(r.get(col))
        if v is not None:
            acc.setdefault(r["id"], []).append(v)
    return {k: sum(v) / len(v) for k, v in acc.items()}


def paired_numeric(arm_rows, base_rows, col):
    """Paired effect of an arm against the base on column ``col``, over the items both have a value for."""
    a, b = per_item(arm_rows, col), per_item(base_rows, col)
    common = sorted(set(a) & set(b))
    diffs = [a[i] - b[i] for i in common]
    better = sum(1 for d in diffs if d > 0)
    worse = sum(1 for d in diffs if d < 0)
    lo, hi = ablate.bootstrap_mean(diffs)
    lo, hi = round(lo, 9), round(hi, 9)
    return {"column": col, "items": len(common), "effect": statistics.mean(diffs) if diffs else 0.0, "lo": lo, "hi": hi, "better": better, "worse": worse,
            "same": len(common) - better - worse, "p_sign": ablate.sign_test(better, worse), "detectable": bool(diffs) and not (lo <= 0 <= hi),
            "arm_only": sorted(set(a) - set(b)), "base_only": sorted(set(b) - set(a))}


def rows_from_run_record(rec, item, arm, seed=1, extra=None):
    """One CSV row from a run record dict: ``tokens_total``, ``real_usd``, ``wall_s_after_slot``, ``reached_stage``, ``verif_stages`` and the stop in
    ``outcome``. ``extra`` adds the experiment's own columns (holes closed, rounds, ...)."""
    stages = rec.get("verif_stages") or {}
    reached = max((i for i, s in enumerate(("V0", "V1", "V2", "V3")) if stages.get(s)), default=-1)
    out = {"id": item, "seed": seed, "arm": arm, "tokens": rec.get("tokens_total"), "cost_usd": rec.get("real_usd"),
           "wall_s": rec.get("wall_s_after_slot"), "stage": rec.get("reached_stage"), "verif_level_reached": reached,
           "stop_reason": rec.get("stop_reason", "")}
    out.update(extra or {})
    return out


def report(rows, base, cols):
    arms = {}
    for r in rows:
        arms.setdefault(r.get("arm", ""), []).append(r)
    if base not in arms:
        raise SystemExit(f"base arm {base!r} not in the rows (arms: {', '.join(arms)})")
    lines = []
    for name, rr in arms.items():
        if name == base:
            continue
        for col in cols:
            p = paired_numeric(rr, arms[base], col)
            lines.append(f"{name} vs {base}, {col}: {p['items']} item(s); effect {p['effect']:+.4g} (95 % interval {p['lo']:+.4g} to {p['hi']:+.4g}); "
                         f"better {p['better']}, worse {p['worse']}, same {p['same']}, sign test p={p['p_sign']:.3g}; "
                         + ("an interval that excludes 0" if p["detectable"] else "no detectable effect"))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--base", required=True)
    ap.add_argument("--col", action="append", required=True)
    a = ap.parse_args(argv)
    rows = [r for p in a.csv for r in load(p)]
    print(report(rows, a.base, a.col))


if __name__ == "__main__":
    main()
