#!/usr/bin/env python3
"""Brief 214: manifest, graded table and mechanism counts from the run records in runs/<n>_<design>_k<k>_<arm>/.
  python3 results/214_cost_routing/analyse.py            writes manifest.tsv (for tools/ab/adapter.py) and mechanism.md
Reads only the committed records (summary.json, role_usage.jsonl, routing_events.jsonl, kway.jsonl); every number printed is from those files."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
RUNS = HERE / "runs"


def load(p: Path):
    try:
        return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def runs():
    for d in sorted(RUNS.glob("*_k*_*"), key=lambda p: int(p.name.split("_")[0])):
        m = re.match(r"(\d+)_(.+)_k(\d+)_(control|routing_kway|routing)$", d.name)
        if not m or not (d / "RUN_ID.txt").exists():
            continue
        n, design, k, arm = m.groups()
        try:
            s = json.loads((d / "summary.json").read_text())
        except (OSError, ValueError):
            s = {}
        yield {"n": int(n), "design": design, "k": k, "arm": arm, "dir": d, "rid": (d / "RUN_ID.txt").read_text().strip(), "summary": s,
               "usage": load(d / "role_usage.jsonl"), "events": load(d / "routing_events.jsonl"), "kway": load(d / "kway.jsonl")}


def mechanism(r) -> dict:
    u, ev = r["usage"], r["events"]
    s = r["summary"]
    tiers: dict[str, dict] = {}
    for x in u:
        t = (x.get("routing") or {}).get("tier", "standard")
        d = tiers.setdefault(t, {"calls": 0, "plan_usd": 0.0, "models": set()})
        d["calls"] += 1
        d["plan_usd"] += x.get("plan_cost_estimate_usd") or 0
        d["models"].add(x.get("model"))
    esc = [x for x in u if (x.get("routing") or {}).get("escalated")]
    visited = s.get("stages_visited") or []
    passed = s.get("stop") == "done"
    cands = [c for c in r["kway"] if "candidate" in c]
    choice = [c for c in r["kway"] if "chosen" in c]
    return {"tiers": tiers, "escalated_calls": len(esc), "escalated_stages": sorted({x["stage"] for x in esc}), "stage2_visits": visited.count(2), "passed": passed,
            "stop": str(s.get("stop") or "")[:70], "kway_rounds": len(choice), "kway_candidates": cands, "kway_choice": choice, "wall_s": s.get("wall_s"),
            "plan_usd": s.get("plan_cost_estimate_usd")}


def main():
    rows = list(runs())
    (HERE / "manifest.tsv").write_text("".join(f"{r['design']}\t{r['k']}\t{r['arm']}\t{r['rid']}\n" for r in rows))
    out = ["# Mechanism counts per run (from role_usage.jsonl, routing_events.jsonl, kway.jsonl)\n",
           "| n | design | k | arm | stage-2 visits | own pass | stop | calls by tier (plan USD) | escalated calls | k-way rounds | candidates (gates passed/findings) | kept | plan USD | wall s |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        m = mechanism(r)
        tiers = "; ".join(f"{t} {d['calls']} ({d['plan_usd']:.2f})" for t, d in sorted(m["tiers"].items()))
        cands = "; ".join(f"{c['candidate']}: {c['gates_passed']}/{c['gates']}, {c['findings']}" for c in m["kway_candidates"]) or "-"
        kept = ", ".join(f"cand {c['chosen']} by {c['decided_by']}{' (own gates only)' if c.get('own_gates_only') else ''}" for c in m["kway_choice"]) or "-"
        out.append(f"| {r['n']} | {r['design']} | {r['k']} | {r['arm']} | {m['stage2_visits']} | {'yes' if m['passed'] else 'no'} | {m['stop'] or '-'} | {tiers} | "
                   f"{m['escalated_calls']} | {m['kway_rounds']} | {cands} | {kept} | {m['plan_usd']} | {m['wall_s']} |")
    (HERE / "mechanism.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    sys.exit(main())
