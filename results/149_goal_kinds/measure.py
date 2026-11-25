"""Brief 149: entry-stage accuracy of the change classifier on the labelled set (no model call, no Vivado).

python3 results/149_goal_kinds/measure.py [--label before|after] -> results/149_goal_kinds/measure_<label>.json
A result is a *question* when classify_change returns no stage for a non-empty request (after the change), and a *silent
stage 0* when it returns stage 0 with no matched word (before the change: the old fallback)."""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.graph.pickup import classify_change   # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--label", default="after")
a = ap.parse_args()
rows = json.loads((Path(__file__).parent / "labelled_requests.json").read_text())
res = []
for r in rows:
    k, s, words = classify_change(r["request"])
    question = s is None
    silent0 = s == 0 and not words
    got_kind = "question" if question else k
    res.append({**r, "got_kind": got_kind, "got_stage": s, "matched": words, "question": question, "silent_stage0": silent0,
                "stage_ok": s == r["stage"], "kind_ok": got_kind == r["kind"]})


def summ(sel):
    n = len(sel)
    return {"n": n, "stage_correct": sum(x["stage_ok"] for x in sel), "kind_correct": sum(x["kind_ok"] for x in sel),
            "silent_stage0": sum(x["silent_stage0"] for x in sel), "questions": sum(x["question"] for x in sel),
            "unmatched_requests_expected_question": sum(1 for x in sel if x["stage"] is None),
            "stage_accuracy": round(sum(x["stage_ok"] for x in sel) / n, 3)}


out = {"label": a.label, "all": summ(res), "dev": summ([x for x in res if x["split"] == "dev"]),
       "check": summ([x for x in res if x["split"] == "check"]),
       "by_kind": {k: summ([x for x in res if x["kind"] == k]) for k in sorted({x["kind"] for x in res})}, "rows": res}
(Path(__file__).parent / f"measure_{a.label}.json").write_text(json.dumps(out, indent=1) + "\n")
for k in ("all", "dev", "check"):
    print(k, {x: out[k][x] for x in ("n", "stage_correct", "kind_correct", "silent_stage0", "questions", "stage_accuracy")})
