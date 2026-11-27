"""Brief 239 step 4: the re-measure. Reads the nine run folders of this worktree (``runs/`` where summary.json names a ``b239_`` design), writes
``after_runs.csv``, ``after_census_table.md`` (the census of their failing gate events), the copied per-run records under ``arms/`` and
``comparison.txt`` (primary and secondary against the baseline of ``baseline_runs.csv``; Wilson intervals; Fisher's exact test, one-sided).

    python results/239_stage2_diagnosis/analyze.py
"""
from __future__ import annotations

import csv
import json
import math
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import census  # noqa: E402

HERE = Path(__file__).parent
W = HERE.parents[1]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def fisher_ge(k1: int, n1: int, k2: int, n2: int) -> float:
    """One-sided P(X >= k1) for the first sample's successes under the hypergeometric null with the pooled successes."""
    from math import comb
    t = k1 + k2
    tot = comb(n1 + n2, t)
    return sum(comb(n1, x) * comb(n2, t - x) for x in range(k1, min(n1, t) + 1)) / tot


def main() -> None:
    runs = []
    for d in sorted((W / "runs").glob("*/summary.json")):
        s = json.loads(d.read_text())
        if str(s.get("design", "")).startswith("b239_"):
            runs.append((s["design"], d.parent, s))
    out = HERE / "arms"
    rows, crows = [], []
    for tag, rd, s in sorted(runs):
        stop = s.get("stop") or ""
        v = s.get("stages_visited") or []
        st = list(rd.glob("*/build/spectest/state.json"))
        sp = json.loads(st[0].read_text()) if st else {}
        cls = "pass" if stop == "done" else ("own-pass, bench not clean" if stop.startswith("unresolved") or "spec-test" in stop else "fail")
        evs = list(census.events(rd))
        lint_rep = 0
        prev: dict = {}
        for ev in evs:
            fs = census.findings(ev)
            cur = {(x["id"], x["where"], x["text"]) for x in fs}
            for x in fs:
                same = (x["id"], x["where"], x["text"]) in prev.get(ev["stage"], set())
                crows.append({"run": f"239/{tag}", "series": "239", "stage": ev["stage"], "visit": ev["visit"], "gate": x["gate"], "id": x["id"], "where": x["where"],
                              "first_line": x["text"], "same_finding_as_previous_visit": int(same), "event_sig": ""})
                lint_rep += int(same and x["gate"] == "lint" and str(ev["stage"]) == "2")
            prev[ev["stage"]] = cur
        rows.append({"run": tag, "class": cls, "own_pass": int(cls != "fail"), "bench_outcome": sp.get("outcome", "not reached"), "bench_built": "" if not sp else int(any(h.get("built") for h in sp.get("history", []))),
                     "stage2_visits": v.count(2), "stage1_visits": v.count(1), "lint_repeats_stage2": lint_rep, "plan_cost_usd": round(s.get("plan_cost_estimate_usd") or 0, 2),
                     "wall_s": s.get("wall_s"), "tokens": s.get("tokens"), "stop": stop[:100]})
        dst = out / tag
        dst.mkdir(parents=True, exist_ok=True)
        for f in ("summary.json", "role_usage.jsonl", "routing_events.jsonl", "config.json"):
            if (rd / f).is_file():
                shutil.copy(rd / f, dst / f)
        for f in rd.glob("*/build/verif_gates.json"):
            shutil.copy(f, dst / "verif_gates.json")
        for f in rd.glob("*/build/spectest/state.json"):
            shutil.copy(f, dst / "spectest_state.json")
    with (HERE / "after_runs.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (HERE / "after").mkdir(exist_ok=True)
    census.summarise(crows, HERE / "after")
    base = list(csv.DictReader((HERE / "baseline_runs.csv").open()))
    a = [b for b in base if b["run"].startswith("227/A")]
    pooled = base
    k, n = sum(r["own_pass"] for r in rows), len(rows)
    ka = sum(b["class"] != "fail" for b in a)
    kp = sum(b["class"] != "fail" for b in pooled)
    lo, hi = wilson(k, n)
    mean = lambda xs: sum(xs) / len(xs)  # noqa: E731
    t = [f"stage-2 own pass: after {k}/{n} (Wilson 95% {lo:.2f} to {hi:.2f}); before, arm A of 227 (same flags): {ka}/{len(a)}; pooled before (213 all, 227 A and C): {kp}/{len(pooled)}",
         f"Fisher one-sided P(>= {k} of {n}) against arm A: {fisher_ge(k, n, ka, len(a)):.3f}; against pooled: {fisher_ge(k, n, kp, len(pooled)):.3f}",
         f"independent bench: clean pass {sum(r['bench_outcome'] == 'pass' for r in rows)}, other outcomes {[r['bench_outcome'] for r in rows]}",
         f"mean stage-2 visits: after {mean([r['stage2_visits'] for r in rows]):.2f}; before A {mean([int(b['stage2_visits']) for b in a]):.2f}; pooled {mean([int(b['stage2_visits']) for b in pooled]):.2f}",
         f"mean stage-1 visits: after {mean([r['stage1_visits'] for r in rows]):.2f}; before A {mean([int(b['stage1_visits']) for b in a]):.2f}; pooled {mean([int(b['stage1_visits']) for b in pooled]):.2f}",
         f"stage-2 repeated lint findings, total: after {sum(r['lint_repeats_stage2'] for r in rows)}; before A {sum(int(b['lint_repeats_stage2']) for b in a)}; pooled {sum(int(b['lint_repeats_stage2']) for b in pooled)}",
         f"mean plan-cost estimate (usd): after {mean([r['plan_cost_usd'] for r in rows]):.2f}; before A {mean([float(b['plan_cost_usd']) for b in a]):.2f}; pooled {mean([float(b['plan_cost_usd']) for b in pooled]):.2f}"]
    (HERE / "comparison.txt").write_text("\n".join(t) + "\n")
    print("\n".join(t))


if __name__ == "__main__":
    main()
