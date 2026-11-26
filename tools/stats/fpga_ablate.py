#!/usr/bin/env python3
"""Brief 216: an adapter from FPGA Force run records to CVDP's ``ablate.py`` / ``table.py`` (copied beside this file, MIT, same author).

FPGA run records are JSON lines (one per run: ``arm``, ``design``, ``seed``, ``status``, ``stop_reason``, and the graded outcomes ``wns_ns``,
``fmax_mhz``, ``vivado_runs``, ``cost``...). ``to_rows`` turns them into the rows ``ablate.py`` reads (``id`` = design, ``pass`` = "1" when the
pre-registered pass rule holds, ``label`` = arm, ``seed``), and drops rows whose stop reason is a plan limit, a rate limit or a refused slot
(``NOT_RUN_STOPS``): they were not run, are listed on stderr, and are re-run, never scored (226 lesson 11).

``paired_numeric`` adds what ``ablate.py`` lacks: the paired effect of any numeric column (a graded outcome such as WNS gain or runs used),
with a paired bootstrap interval over designs, a better/worse/same count and the exact sign test (all of them ``ablate.py``'s own functions).

    python3 tools/stats/fpga_ablate.py records.jsonl --base control --column wns_gain_ns [--pass-rule 'wns_ns>=0']
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ablate  # noqa: E402  (the copy beside this file)

#: stop reasons that mean the run did not happen: it is re-run, never scored as a failure
NOT_RUN_STOPS = ("rate_limited", "plan_limit", "profile_error", "slot_refused", "usage_stop")


def load_records(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def split_not_run(records: list[dict]) -> tuple[list[dict], list[dict]]:
    ran = [r for r in records if r.get("stop_reason") not in NOT_RUN_STOPS]
    skipped = [r for r in records if r.get("stop_reason") in NOT_RUN_STOPS]
    if skipped:
        print(f"fpga_ablate: {len(skipped)} record(s) not run (plan, rate or slot stop) left out; re-run them", file=sys.stderr)
    return ran, skipped


def to_rows(records: list[dict], passed=lambda r: r.get("wns_ns") is not None and r["wns_ns"] >= 0 and (r.get("whs_ns") or 0) >= 0) -> dict[str, list[dict]]:
    """{arm: [ablate.py rows]}."""
    ran, _ = split_not_run(records)
    arms: dict[str, list[dict]] = {}
    for r in ran:
        arms.setdefault(r["arm"], []).append({"id": r["design"], "pass": "1" if passed(r) else "0", "label": r["arm"], "seed": str(r.get("seed", 1)),
                                              "_run": f"{r['arm']}#seed{r.get('seed', 1)}", "cost_usd": r.get("cost", ""),
                                              "wall_time_s": r.get("wall_s", ""), "stop_reason": r.get("stop_reason", "")})
    return arms


def paired_numeric(records: list[dict], arm: str, base: str, column: str, level: float = 0.95) -> dict:
    """Paired effect of ``column`` (arm minus base), mean over the designs both have (a design's runs averaged), with a paired bootstrap interval."""
    ran, _ = split_not_run(records)

    def per_design(a: str) -> dict[str, float]:
        acc: dict[str, list[float]] = {}
        for r in ran:
            if r["arm"] == a and r.get(column) is not None:
                acc.setdefault(r["design"], []).append(float(r[column]))
        return {k: statistics.mean(v) for k, v in acc.items()}

    a, b = per_design(arm), per_design(base)
    common = sorted(set(a) & set(b))
    diffs = [a[d] - b[d] for d in common]
    lo, hi = ablate.bootstrap_mean(diffs, level=level) if diffs else (0.0, 0.0)
    better, worse = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    return {"column": column, "arm": arm, "base": base, "designs": len(common), "effect": statistics.mean(diffs) if diffs else None,
            "lo": lo, "hi": hi, "better": better, "worse": worse, "same": len(diffs) - better - worse, "p_sign": ablate.sign_test(better, worse),
            "per_design": dict(zip(common, diffs))}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("records")
    ap.add_argument("--base", required=True)
    ap.add_argument("--column", action="append", default=[])
    a = ap.parse_args(argv)
    recs = load_records(a.records)
    for arm in sorted({r["arm"] for r in recs} - {a.base}):
        for col in a.column:
            print(json.dumps(paired_numeric(recs, arm, a.base, col)))


if __name__ == "__main__":
    main()
