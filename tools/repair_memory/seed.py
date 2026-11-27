#!/usr/bin/env python3
"""Brief 217: make repair records from the replay's transitions (``replay.py extract`` output) for a reviewed batch to the knowledge bank.

A record is made from a transition of one run: a key that failed at stage-2 evaluation i and no longer fails at i+1, with at least one file changed
by the visit between them. Only the pilots' own runs are used (sources 213, 209, 209a, 224); the 215 benchmark runs are never recorded from.
Records carry ``provenance: agent-repair``, ``produced_by: agent`` and ``reviewed: false``; a person reviews the batch before it is merged.

    python tools/repair_memory/seed.py results/217_repair_memory/replay_evals.jsonl --out <knowledge bank>/repairs/records
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent.graph import repair_memory as rm  # noqa: E402

SOURCES = ("213", "209", "209a", "224")


def stamp_of(run: str) -> str:
    d, _, t = run.partition("-")
    t = t.split("-")[0]
    return f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:4]}:{t[4:6]} GMT"


def make(rows: list[dict]) -> list[dict]:
    by: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        by[r["run"]].append(r)
    out: list[dict] = []
    for run, ev in sorted(by.items()):
        ev.sort(key=lambda r: r["i"])
        if ev[0]["source"] not in SOURCES:
            continue
        for a, b in zip(ev, ev[1:]):
            fx = b.get("fix_from_previous")
            if a["passed"] or not fx or not fx["files"]:
                continue
            still = {rm.key_tuple(k) for k in b["keys"]}
            passed_gates = sorted({k["gate"] for k in a["keys"]} - {k["gate"] for k in b["keys"]})
            for k in a["keys"]:
                if rm.key_tuple(k) in still:
                    continue
                rec = rm.make_record(k, fx, run_id=run, design=a["design"] or run, gates_after=passed_gates + (["all stage-2 gates"] if b["passed"] else []),
                                     visit=a["i"] + 2, ts=stamp_of(run))
                rec["design_family"] = a["design"] or rec["design_family"]
                rec["seeded_from"] = f"replay of the run's per-gate snapshots, evaluations {a['i']} to {b['i']} (brief 217)"
                out.append(rec)
    return out


def main() -> int:
    from agent.access import require_or_exit      # brief 94: the replay builds sessions; the seed reads the agent's records
    require_or_exit("tools.repair_memory.seed")
    ap = argparse.ArgumentParser()
    ap.add_argument("evals", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    recs = make([json.loads(x) for x in a.evals.read_text().splitlines()])
    a.out.mkdir(parents=True, exist_ok=True)
    for r in recs:
        (a.out / f"{r['id']}.json").write_text(json.dumps(r, indent=1) + "\n")
    print(f"{len(recs)} records written to {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
