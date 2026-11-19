#!/usr/bin/env python3
"""The plan-repeatability score (brief 106): how often the same request, run again, gives the same *plan* and the same
*derived parameters*. The RTL is not compared: a generative step is allowed to differ.

A run record contributes two things:

- **the stage plan**: the order in which the stage machine visited stages, with consecutive repeats collapsed
  (``[0, 0, 1, 1, 2, 2, 2]`` is the plan ``0 > 1 > 2``). The stage order is fixed by code (agent/graph/stages.py), so a model can
  change how often a stage is repeated and where the run stops, not the order. Both are reported: ``plan`` (the collapsed order,
  up to where the run stopped) and ``visits`` (the full sequence, which includes the model-driven repair loops).
- **the derived parameters**: the table ``flow/derived_constants.py`` derives for the design, here the shell design ID the RTL
  binds. They are repeatable when every repeat binds the value the spec derives (a repeat is a pair of runs with equal values).

A repeat group is the runs of one task and arm. Pairs inside a group are compared; a run with no stage record (killed at the hard
limit before the record was written) is counted as ``no_plan`` and left out of the pairs, never counted as a match.

    python3 -m flow.plan_repeat benchmark/v2/runs/b82p3 [benchmark/v2/runs/b82p2 ...]
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from typing import Any


def collapse(seq: list[int]) -> tuple[int, ...]:
    return tuple(k for k, _ in itertools.groupby(seq))


def pair_rate(values: list[Any]) -> tuple[int, int]:
    """(pairs that are equal, pairs) over the non-None values."""
    vs = [v for v in values if v is not None]
    pairs = list(itertools.combinations(vs, 2))
    return sum(1 for a, b in pairs if a == b), len(pairs)


def score(groups: dict[str, list[dict[str, Any]]], expected: dict[str, Any] | None = None) -> dict[str, Any]:
    """``groups``: key -> run dicts with ``stages_visited`` (list or None) and optionally ``params`` (a hashable value or None).
    ``expected``: key -> the value the spec derives for ``params``; the group then also reports how many runs bound it."""
    out: dict[str, Any] = {"groups": {}, "total": {}}
    tot = {"plan": [0, 0], "visits": [0, 0], "params": [0, 0], "correct": [0, 0]}
    expected = expected or {}
    for k, runs in sorted(groups.items()):
        sv = [r.get("stages_visited") for r in runs]
        plans = [collapse(s) if s else None for s in sv]
        visits = [tuple(s) if s else None for s in sv]
        params = [r.get("params") for r in runs]
        g = {"runs": len(runs), "no_plan": sum(1 for s in sv if not s),
             "plans": [list(p) if p else None for p in plans], "visit_counts": [len(s) if s else None for s in sv]}
        for name, vals in (("plan", plans), ("visits", visits), ("params", params)):
            eq, n = pair_rate(vals)
            g[name] = {"equal_pairs": eq, "pairs": n}
            tot[name][0] += eq
            tot[name][1] += n
        if expected.get(k) is not None:
            have = [v for v in params if v is not None]
            ok = sum(1 for v in have if v == expected[k])
            g["correct"] = {"equal_pairs": ok, "pairs": len(have)}          # here "pairs" is runs with a binding
            tot["correct"][0] += ok
            tot["correct"][1] += len(have)
        out["groups"][k] = g
    out["total"] = {n: {"equal_pairs": a, "pairs": b, "rate": (a / b if b else None)} for n, (a, b) in tot.items()}
    return out


def load_records(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Group a driver's ``records/*.json`` by task (and arm, when the run has arms)."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for f in sorted((run_dir / "records").glob("*.json")):
        r = json.loads(f.read_text())
        key = f"{run_dir.name}:{r.get('task', f.stem)}" + (f":{r['arm']}" if r.get("arm") else "")
        groups.setdefault(key, []).append({"run_id": r.get("run_id"), "stages_visited": r.get("stages_visited")})
    return groups


def main(argv: list[str]) -> int:
    groups: dict[str, list[dict[str, Any]]] = {}
    for d in argv:
        groups.update(load_records(Path(d)))
    print(json.dumps(score(groups), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
