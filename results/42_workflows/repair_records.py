#!/usr/bin/env python3
"""Amendment 5: re-derive a record's run-dependent fields from its run directory.

Two workers started in the same second (2026-11-11 14:32:01) both took the lexically first new run directory as theirs, so the
H9 record of t1_gray_stepper repeat 1 pointed at the H2 run's directory. This script fixes a record by naming the right run id:
    python3 repair_records.py <task> <seed> <arm> <run_id>
The run's config.json must name the task and arm. Everything else in the record (wall time, worker) is kept; tokens, cost,
stages, audit metrics and the hidden-bench score are recomputed from the run directory, as driver.one_run does.
"""
import fcntl
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import driver  # noqa: E402


def main(task, seed, arm, rid, root):
    root = Path(root)
    run = root / "runs" / rid
    cfg = json.loads((run / "config.json").read_text())
    assert cfg["name"] == task and (cfg.get("harness_arms") or "") in (driver.ARMS[arm], "") and (arm == "A0") == (not cfg.get("harness_arms")), cfg
    with open(driver.LOG, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        rows = [json.loads(x) for x in f.read().splitlines() if x.strip()]
        i = next(i for i, r in enumerate(rows) if (r["task"], r["seed"], r["arm"]) == (task, int(seed), arm) and not r.get("repaired"))
        rec = rows[i]
        for k in ("cost_usd", "tokens", "turns", "stop", "stage2_visits", "stage2_gates_passed", "unreported_cost_calls", "per_stage",
                  "error", "infra_failure", "cost_lower_bound"):
            rec.pop(k, None)
        rec["run_id"] = rid
        s = json.loads((run / "summary.json").read_text())
        rec.update(cost_usd=s.get("cost_usd"), tokens=s.get("tokens"), turns=s.get("turns"), stop=s.get("stop"),
                   stage2_visits=sum(1 for n in s.get("stages_visited", []) if n == 2),
                   stage2_gates_passed=bool((s.get("gates_last") or {}).get("rtl-design-creation")),
                   unreported_cost_calls=s.get("unreported_cost_calls"),
                   per_stage={k: {"tokens": v["tokens"], "cost_usd": v["cost_usd"], "calls": v["calls"]} for k, v in (s.get("per_stage") or {}).items()})
        design = run / task
        rec.update(driver.audit_metrics(design))
        rec["score"] = driver.score(root, driver.TASKS[task], design / "rtl", HERE / "scores" / f"{rid}.json")
        rec["repaired"] = "run directory re-derived (same-second start collision), amendment 5"
        f.seek(0)
        f.truncate()
        f.write("".join(json.dumps(r) + "\n" for r in rows))
    print(json.dumps({k: rec.get(k) for k in ("task", "arm", "run_id", "cost_usd", "tokens", "stop", "score")}))


if __name__ == "__main__":
    main(*sys.argv[1:5], root=sys.argv[5])
