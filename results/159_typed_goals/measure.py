"""Brief 159: ten scripted goal changes, three arms (full re-run, F1 = brief 149's classify_change on the goal text, F5 = agent revise).

python3 results/159_typed_goals/measure.py  ->  results/159_typed_goals/measure.json
Dry runs only: no model call, no Vivado, no simulation, no spend. The labels (labelled_changes.json) were committed before the planner existed
(see PREREGISTRATION.md). 'stages re-run' counts stages 0 to 9 from the entry stage; 'builds' is one when the entry is at or before stage 3 (the
first Vivado build is stage 3 onward). F5's number is the stage the GOAL CHANGE itself needs (`goal_stage`): on these worktree checkouts the handover
also reports added files (for example __init__.py) that pull a `resume` or `revise` entry to stage 2 for every arm alike; that noise is recorded
per change (`entry_stage_with_worktree_noise`) but is not what the arms differ in."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.graph import goals as G, pickup, revise as R   # noqa: E402

HERE = Path(__file__).parent
rows = json.loads((HERE / "labelled_changes.json").read_text())
FULL = R.FULL_RERUN_STAGES
loaded: dict[str, dict] = {}
out = []
for r in rows:
    d = ROOT / "designs" / r["design"]
    ld = loaded.setdefault(r["design"], pickup.load(d))
    goals = [G.parse_goal(t) for t in r["goals"]]
    pl = R.plan(d, ld, goals, r["retarget"])
    text = " ".join(r["goals"] + ([f"retarget to {r['retarget']}"] if r["retarget"] else []))
    k, f1_stage, words = pickup.classify_change(text)
    f5_stage = pl["goal_stage"]
    req = r["required"]

    def arm(stage):
        return {"entry_stage": stage, "stages_rerun": 0 if stage is None else FULL - stage, "builds": int(stage is not None and stage <= 3)}

    def sound(stage):             # no stale evidence kept: the entry is not later than the stage the change needs
        return True if req == "met" else (stage is not None and stage <= req)

    def exact(stage):
        return stage is None if req == "met" else stage == req

    arms = {"full": {**arm(0), "sound": True, "exact": False},
            "F1": {**arm(f1_stage), "kind": k, "matched": words, "sound": sound(f1_stage), "exact": exact(f1_stage)},
            "F5": {**arm(f5_stage), "verdicts": [c["verdict"] for c in pl["changes"]] + ([pl["retarget"]["verdict"]] if pl["retarget"] else []),
                   "sound": sound(f5_stage), "exact": exact(f5_stage), "entry_stage_with_worktree_noise": pl["entry"]["stage"],
                   "evidence_used": [c["evidence"]["measurement"] for c in pl["changes"] if c.get("evidence", {}).get("measurement") and c["verdict"] == "met_by_evidence"]}}
    out.append({"id": r["id"], "design": r["design"], "goals": r["goals"], "retarget": r["retarget"], "required": req, "arms": arms})


def tot(a):
    return {"stages_rerun": sum(x["arms"][a]["stages_rerun"] for x in out), "builds": sum(x["arms"][a]["builds"] for x in out),
            "unsound": sum(not x["arms"][a]["sound"] for x in out), "exact": sum(x["arms"][a]["exact"] for x in out)}


summary = {a: tot(a) for a in ("full", "F1", "F5")}
f1, f5 = summary["F1"]["stages_rerun"], summary["F5"]["stages_rerun"]
summary["F5_vs_F1_stages_saved_pct"] = round(100 * (f1 - f5) / f1, 1)
summary["F5_vs_full_stages_saved_pct"] = round(100 * (summary["full"]["stages_rerun"] - f5) / summary["full"]["stages_rerun"], 1)
summary["pass"] = {"unsound_0": summary["F5"]["unsound"] == 0, "at_least_15pct_below_F1": summary["F5_vs_F1_stages_saved_pct"] >= 15,
                   "every_plan_equals_its_label": summary["F5"]["exact"] == len(out)}
(HERE / "measure.json").write_text(json.dumps({"n": len(out), "summary": summary, "rows": out}, indent=1) + "\n")
print(json.dumps(summary, indent=1))
for x in out:
    print(x["id"], x["design"][:14], x["goals"] or x["retarget"], "req", x["required"], "|", " ".join(f"{a}:{v['entry_stage']}" for a, v in x["arms"].items()))
