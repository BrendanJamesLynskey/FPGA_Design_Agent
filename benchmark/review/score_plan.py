#!/usr/bin/env python3
"""Runs and scores the improvement-request plan test (brief 84, phase 1). Code only.

    score_plan.py --bench <review84 dir> --out <dir> --claude-bin <bin> [--k 3]      run then score (cases in improvements.yaml)
    score_plan.py --bench <review84 dir> --out <dir> --score-only

A plan is SOUND for a case when every check passes: the measurable flag equals the expected one; a measurable item has an
acceptance test and an unmeasurable one has a question; when the case names a planted issue, the plan's item depends_on a review
finding that matches that issue (benchmark/review/score.fits) and the ordered steps put that finding before the request; the item
has an entry stage; needs_build, when expected, is true in the cost. Plans only: nothing is carried out.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmark.review import score as S  # noqa: E402


def check(case: dict, rep: dict, truth: dict) -> dict:
    exp = case["expect"]
    imp = rep.get("improvements") or {}
    items = imp.get("items") or []
    res = {"case": case["id"], "checks": {}, "sound": False}
    if not items:
        res["checks"]["has_item"] = False
        return res
    it = items[0]
    g, a = it.get("goal") or {}, it.get("assessment") or {}
    c = res["checks"]
    c["has_item"] = True
    c["measurable_as_expected"] = bool(it.get("measurable", True)) == exp["measurable"]
    c["test_or_question"] = bool(str(g.get("acceptance_test", "")).strip()) if exp["measurable"] else bool(str(it.get("question", "")).strip())
    c["entry_stage_set"] = it.get("entry", {}).get("stage") is not None
    if exp.get("needs_build"):
        c["needs_build"] = bool((a.get("cost") or {}).get("needs_build"))
    if exp.get("depends_on_issue"):
        issue = next(i for i in truth["issues"] if i["id"] == exp["depends_on_issue"])
        fids = [f["id"] for f in rep["findings"] if f["severity"] != "info" and S.fits(f, issue)]
        dep = [d for d in a.get("depends_on") or [] if d in fids]
        c["depends_on_matching_finding"] = bool(dep)
        steps = (imp.get("order") or {}).get("steps") or []
        c["finding_ordered_first"] = bool(dep) and f"fix finding {dep[0]} first" in steps and steps.index(f"fix finding {dep[0]} first") < steps.index(f"request {it['id']}") if f"request {it['id']}" in steps else False
    res["sound"] = all(c.values())
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--claude-bin", default="claude")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--score-only", action="store_true")
    a = ap.parse_args()
    from flow.review import review
    cases = yaml.safe_load((a.bench / "improvements.yaml").read_text())["cases"]
    truth = S.load_truth(a.bench)
    out = []
    for c in cases:
        for k in range(1, a.k + 1):
            d = a.out / c["id"] / f"r{k}"
            if not (d / "review.json").is_file() and not a.score_only:
                review(a.bench / "designs" / c["design"], d, improvements=[c["request"]], claude_bin=a.claude_bin,
                       name=f"{c['design']}_{c['id']}_r{k}", tag=f"{c['id']}_r{k}")
            try:
                rep = json.loads((d / "review.json").read_text())
            except OSError:
                out.append({"case": c["id"], "k": k, "sound": False, "checks": {"not_run": True}})
                continue
            r = check(c, rep, truth[c["design"]])
            r["k"] = k
            out.append(r)
    by = {}
    for r in out:
        by.setdefault(r["case"], []).append(r["sound"])
    summ = {c: {"sound": sum(v), "runs": len(v), "wilson95_per_run": list(S.wilson(sum(v), len(v)))} for c, v in by.items()}
    tot = sum(r["sound"] for r in out)
    res = {"plans": len(out), "sound": tot, "sound_rate": round(tot / len(out), 3) if out else None, "by_case": summ, "detail": out}
    (a.out / "plan_scores.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "detail"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
