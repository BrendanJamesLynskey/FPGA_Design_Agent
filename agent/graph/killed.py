"""Brief 82P7: the ``summary.json`` of a run that was stopped from outside (the benchmark driver's wall limit, a kill).

A run that ends on its own writes ``summary.json`` from the graph's state (``agent.graph.run.summary``). A run killed by the driver at
its hard limit writes nothing: 82P6 had no cost, no stop reason and no last state for four of its six runs, and a post-hoc file
(``killed_runs_state.json``) had to be made from the run directory. This module builds the same record from the files the run left
(``role_usage.jsonl``, ``claude_code_calls.jsonl``, ``snapshots.json``, ``routing_events.jsonl``, the design's ``build/audit.jsonl`` and
spec-test state). It never overwrites a summary the graph wrote.

    python -m agent.graph.killed <run dir> --wall-limit-s 14400 [--wall-s 14400.6]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

STAGE2 = "rtl-design-creation"


def _lines(p: Path) -> list[dict]:
    try:
        return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def _design_dir(run_dir: Path) -> Path | None:
    for p in sorted(run_dir.iterdir()):
        if p.is_dir() and (p / "build" / "audit.jsonl").is_file():
            return p
    return None


def _by(rows: list[dict], key: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for u in rows:
        d = out.setdefault(str(u[key]), {"calls": 0, "turns": 0, "tokens": 0, "wall_s": 0.0, "cost_usd": 0.0, "plan_cost_estimate_usd": 0.0})
        d["calls"] += 1
        d["turns"] += u.get("turns") or 0
        d["tokens"] += u.get("tokens") or 0
        d["wall_s"] = round(d["wall_s"] + (u.get("wall_s") or 0), 1)
        d["cost_usd"] = round(d["cost_usd"] + (u.get("cost_usd") or 0), 6)
        d["plan_cost_estimate_usd"] = round(d["plan_cost_estimate_usd"] + (u.get("plan_cost_estimate_usd") or 0), 4)
    return out


def killed_summary(run_dir: Path, wall_limit_s: float, wall_s: float | None = None) -> dict[str, Any]:
    """The summary of a run stopped from outside, from its run directory. Facts only; ``stop`` starts with ``budget`` and
    ``clean_stop`` is false."""
    cfg = {}
    try:
        cfg = json.loads((run_dir / "config.json").read_text())
    except (OSError, ValueError):
        pass
    usage = _lines(run_dir / "role_usage.jsonl")
    calls = _lines(run_dir / "claude_code_calls.jsonl")
    snaps = []
    try:
        snaps = json.loads((run_dir / "snapshots.json").read_text())
    except (OSError, ValueError):
        pass
    design = _design_dir(run_dir)
    audit = _lines(design / "build" / "audit.jsonl") if design else []
    stage2_visits = max([int(u["visit"]) for u in usage if u.get("stage") == STAGE2] or [0])
    sim_s: dict[str, float] = defaultdict(float)
    for a in audit:
        if a.get("tool") == "simulate" and a.get("role") is None:
            sim_s["gate_icarus" if (a.get("arguments") or {}).get("sim") == "icarus" else "gate_verilator"] += a.get("seconds") or 0
    last_role = usage[-1] if usage else {}
    spec_test = {}
    if design is not None:
        try:
            from agent.graph import spectest
            spec_test = spectest.record(design) if cfg.get("spec_tests") or (design / "build" / "spectest" / "state.json").is_file() else {}
        except Exception:                                    # noqa: BLE001 (a record that cannot be read is left out)
            spec_test = {}
    verif_reached = None
    if design is not None:
        try:
            verif_reached = json.loads((design / "build" / "verif" / "verif_gates.json").read_text()).get("reached")
        except (OSError, ValueError):
            pass
    why = (f"budget: the wall limit of {wall_limit_s:.0f} s was reached and the run was stopped from outside; stage 2 had {stage2_visits} "
           f"visit(s); no clean evaluation had passed")
    return {
        "run_id": run_dir.name, "design": cfg.get("name"), "killed": True,
        "stop": why,
        "stop_detail": {"kind": "wall_limit", "wall_limit_s": wall_limit_s, "wall_s": wall_s, "stage2_visits": stage2_visits,
                        "last_role_call": {k: last_role.get(k) for k in ("stage", "visit", "role", "ended", "wall_s")},
                        "last_verif_reached": verif_reached, "gate_simulation_s": {k: round(v, 1) for k, v in sim_s.items()}},
        "clean_stop": False,
        "tokens": sum(u.get("tokens") or 0 for u in usage), "turns": sum(u.get("turns") or 0 for u in usage),
        "cost_usd": round(sum(u.get("cost_usd") or 0 for u in usage), 6),
        "plan_cost_estimate_usd": round(sum(c.get("plan_cost_estimate_usd") or 0 for c in calls), 4),
        "wall_s": wall_s, "stages_visited": [s.get("n") for s in snaps],
        "gates_last": {}, "per_role": _by(usage, "role"), "per_stage": _by(usage, "stage"),
        "routing_events": _lines(run_dir / "routing_events.jsonl"), "spec_test": spec_test,
        "claude_code_version": (calls[0].get("claude_code_version") if calls else None),
        "written_by": "agent.graph.killed (the run did not end on its own)"}


def write_killed_summary(run_dir: Path, wall_limit_s: float, wall_s: float | None = None) -> Path | None:
    """Write ``<run dir>/summary.json`` for a stopped run; None (and nothing written) if the graph already wrote one."""
    out = run_dir / "summary.json"
    if out.is_file():
        return None
    out.write_text(json.dumps(killed_summary(run_dir, wall_limit_s, wall_s), indent=1))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--wall-limit-s", type=float, required=True)
    ap.add_argument("--wall-s", type=float)
    a = ap.parse_args(argv)
    p = write_killed_summary(Path(a.run_dir), a.wall_limit_s, a.wall_s)
    print(str(p) if p else "summary.json already exists; left as it is")
    return 0


if __name__ == "__main__":
    sys.exit(main())
