"""Brief 213: FPGA agent run records -> the CSV rows tools/ab/ablate.py and tools/ab/paired_numeric.py read (the 226 report's "30-line adapter").

One row per agent run. Columns: ``id`` (the design), ``seed`` (the replicate number k), ``label`` (the arm), ``pass`` (1 when the run's own stage-2 gates all
passed: an own-check verdict, NOT an independent check), ``indep`` (the independent check: empty until a check exists, never filled by the agent's own
gates), ``stop_reason`` (``rate_limited`` and ``slot_refused`` rows are left out by ablate.py, never scored as failures), ``cost_usd`` (the agent's plan
estimate for Claude Code runs, provider-reported dollars otherwise), ``wall_time_s``, and the graded outcomes: ``stage2_visits`` (stage-2 visits the run used;
a run that did not pass stage 2 counts the visit limit plus one), ``stage_reached``, ``vivado_runs``.

  python3 tools/ab/adapter.py RUNS_ROOT MANIFEST.tsv > runs.csv      MANIFEST: design<TAB>k<TAB>arm<TAB>run_id<TAB>stop_override(optional)
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

COLS = ["id", "seed", "label", "pass", "indep", "stop_reason", "cost_usd", "wall_time_s", "stage2_visits", "stage_reached", "vivado_runs", "run_id"]
STAGE2_LIMIT = 6        # visit_limit(2) in agent/graph/run.py, the value a non-passing run is scored at plus one


def row(runs_root: Path, design: str, k: str, arm: str, run_id: str, stop_override: str = "") -> dict:
    d = Path(runs_root) / run_id
    try:
        s = json.loads((d / "summary.json").read_text())
    except (OSError, ValueError):
        return {"id": design, "seed": k, "label": arm, "pass": "", "stop_reason": stop_override or "no_record", "run_id": run_id}
    visited = s.get("stages_visited") or []
    n2 = visited.count(2)
    stop = str(s.get("stop") or "")
    passed = stop == "done" and 2 in visited          # --stop-after 2 ends a passing run with stop "done"; any other stop is not a pass
    reached = max(visited) if visited else ""
    return {"id": design, "seed": k, "label": arm, "pass": "1" if passed else "0", "indep": "", "stop_reason": stop_override or stop[:60],
            "cost_usd": s.get("plan_cost_estimate_usd") if s.get("plan_cost_estimate_usd") is not None else s.get("cost_usd"),
            "wall_time_s": s.get("wall_s"), "stage2_visits": (n2 if passed else STAGE2_LIMIT + 1), "stage_reached": reached,
            "vivado_runs": "", "run_id": run_id}


def main(argv: list[str]) -> None:
    root, manifest = Path(argv[1]), Path(argv[2])
    w = csv.DictWriter(sys.stdout, fieldnames=COLS)
    w.writeheader()
    for ln in manifest.read_text().splitlines():
        p = ln.split("\t")
        if len(p) >= 4 and not ln.startswith("#"):
            w.writerow(row(root, *p[:4], *(p[4:5] or [""])))


if __name__ == "__main__":
    main(sys.argv)
