#!/usr/bin/env python3
"""Scores design reviews against planted ground truth (brief 84). Code only: no model produces a score.

    score.py --truth <review84 dir> --reviews <dir of arm/<id>/r<k>/review.json> --arm agent|baseline [--split heldout] --out <dir>

Matching rule (pre-registered, results/84_review/prereg.md):
- Only findings of severity critical, major or minor are scored; ``info`` findings are counted and ignored.
- A finding FOUND a planted issue when (a) its category is one the issue accepts, or its rule code is one of the issue's tool
  codes, AND (b) its location is inside one of the issue's regions: the same file, and for a region with lines, the finding's
  line (or any line of its range) within LINE_TOL lines of the region; a region without lines is the whole file, and a
  finding with no line number matches only such a region; AND (c) when the issue lists ``keywords`` (the issues whose region is a
  whole file), the finding's title, evidence, fix or rule contains at least one of them.
- Each finding is used for at most one issue and each issue is found at most once per review: further findings on an issue that
  is already found are duplicates (not false alarms, not extra recall). When several findings fit an issue, the one with the
  closest severity wins, then the higher confidence, then the lower id.
- A finding that matches no issue is a FALSE ALARM unless the design lists a benign region for it (file and category) and the
  finding is not above minor. False alarms are counted strictly here; the adjudication step reads them afterwards and may list
  some as real unplanted defects (``adjudication.yaml``), which are reported on their own and never added to recall.
- Recall is over issue-reviews: planted issues x repeats. Precision is found / (found + false alarms), over scored findings.
- Severity accuracy: of the found issues, the share where the finding's severity equals the issue's, and the share within one level.
- Missing or invalid review files are NOT RUN, counted and listed; for recall they count as missed (they stay in the
  denominator) unless ``--drop-missing`` is given, so a crashed run is never silently dropped.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

LINE_TOL = 2
SEV = {"critical": 0, "major": 1, "minor": 2, "info": 3}
CONF = {"high": 0, "medium": 1, "low": 2}
BOOT = 2000
SEED = 84


def load_truth(truth_dir: Path) -> dict[str, dict[str, Any]]:
    return {p.stem: yaml.safe_load(p.read_text()) for p in sorted((truth_dir / "truth").glob("rb*.yaml"))}


def _norm(f: str) -> str:
    return (f or "").replace("\\", "/").lstrip("./")


def in_region(finding: dict[str, Any], reg: dict[str, Any]) -> bool:
    loc = finding["location"]
    ff, rf = _norm(loc.get("file")), _norm(reg["file"])
    if not ff or not (ff == rf or ff.endswith("/" + rf) or rf.endswith("/" + ff)):
        return False
    if "lines" not in reg:
        return True
    ln = loc.get("line")
    if not ln:
        return False
    lo, hi = reg["lines"]
    a, b = int(ln), int(loc.get("end_line") or ln)
    return a <= hi + LINE_TOL and b >= lo - LINE_TOL


def fits(finding: dict[str, Any], issue: dict[str, Any]) -> bool:
    code = (finding.get("rule") or "")
    ok_cat = finding["category"] in issue["categories"] or any(c in code for c in issue.get("tool_codes") or [])
    kws = issue.get("keywords") or []
    text = " ".join(str(finding.get(k, "")) for k in ("title", "evidence", "fix", "rule")).lower()
    ok_kw = not kws or any(k.lower() in text for k in kws)     # an issue with a whole-file region names words the finding must use
    return ok_cat and ok_kw and any(in_region(finding, r) for r in issue["regions"])


def score_review(review: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    """One review against one design's truth. Returns found issues, false alarms, benign, duplicates, ignored info."""
    fs = [f for f in review["findings"] if f["severity"] in ("critical", "major", "minor")]
    info = [f for f in review["findings"] if f["severity"] == "info"]
    used: set[str] = set()
    found: dict[str, dict[str, Any]] = {}
    for issue in truth["issues"]:
        cands = [f for f in fs if f["id"] not in used and fits(f, issue)]
        if not cands:
            continue
        cands.sort(key=lambda f: (abs(SEV[f["severity"]] - SEV[issue["severity"]]), CONF.get(f["confidence"], 1), f["id"]))
        found[issue["id"]] = cands[0]
        used.add(cands[0]["id"])
    dup, fa, benign = [], [], []
    for f in fs:
        if f["id"] in used:
            continue
        if any(fits(f, i) for i in truth["issues"]):
            dup.append(f["id"])
        elif any(_norm(f["location"].get("file")) == _norm(b["file"]) and f["category"] in b["cats"] and SEV[f["severity"]] >= 2 for b in truth.get("benign") or []):
            benign.append(f["id"])
        else:
            fa.append(f["id"])
    sev_exact = sum(1 for i in truth["issues"] if i["id"] in found and found[i["id"]]["severity"] == i["severity"])
    sev_one = sum(1 for i in truth["issues"] if i["id"] in found and abs(SEV[found[i["id"]]["severity"]] - SEV[i["severity"]]) <= 1)
    return {"found": sorted(found), "missed": sorted(i["id"] for i in truth["issues"] if i["id"] not in found), "false_alarms": fa,
            "duplicates": dup, "benign": benign, "info_ignored": len(info), "scored_findings": len(fs), "severity_exact": sev_exact,
            "severity_within_one": sev_one}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(max(0.0, c - h), 3), round(min(1.0, c + h), 3))


def boot(per_design: dict[str, tuple[float, float]], fn, n: int = BOOT) -> tuple[float, float]:
    """Percentile 95% interval of fn(list of (a, b)) with designs resampled (the unit is the design, not the run)."""
    rng = random.Random(SEED)
    ids = sorted(per_design)
    vals = []
    for _ in range(n):
        s = [per_design[rng.choice(ids)] for _ in ids]
        v = fn(s)
        if v is not None:
            vals.append(v)
    vals.sort()
    if not vals:
        return (float("nan"), float("nan"))
    return (round(vals[int(0.025 * len(vals))], 3), round(vals[min(len(vals) - 1, int(0.975 * len(vals)))], 3))


def collect(truth: dict[str, dict], reviews: Path, arm: str, split: str, k: int | None) -> dict[str, Any]:
    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    notrun: list[str] = []
    cost = {"reviews": 0, "total_tokens": 0, "output_tokens": 0, "wall_s": 0.0}
    for rid, t in truth.items():
        if split != "all" and t["split"] != split:
            continue
        for kk in range(1, (k or 3) + 1):
            p = reviews / arm / rid / f"r{kk}" / "review.json"
            try:
                rev = json.loads(p.read_text())
                if "findings" not in rev:
                    raise ValueError("no findings key")
            except (OSError, ValueError):
                notrun.append(f"{rid}/r{kk}")
                continue
            if arm == "agent" and not rev.get("judge", {}).get("ran"):
                notrun.append(f"{rid}/r{kk} (the reviewer's reply was not usable)")
                continue
            s = score_review(rev, t)
            s["rid"], s["k"] = rid, kk
            runs[rid].append(s)
            c = (rev.get("judge") or {}).get("call") or {}
            u = c.get("usage") or {}
            cost["reviews"] += 1
            cost["total_tokens"] += int(u.get("total_tokens") or 0)
            cost["output_tokens"] += int(u.get("output_tokens") or 0)
            cost["wall_s"] += float(c.get("wall_s") or 0) or float(rev.get("seconds") or 0)
    return {"runs": runs, "not_run": notrun, "cost": cost, "split": split}


def summarise(truth: dict[str, dict], col: dict[str, Any], k: int, count_missing: bool) -> dict[str, Any]:
    runs = col["runs"]
    sel = {rid: t for rid, t in truth.items() if col["split"] == "all" or t["split"] == col["split"]}
    by_class: dict[str, dict[str, int]] = defaultdict(lambda: {"issue_reviews": 0, "found": 0, "found_in_any": 0, "found_in_all": 0, "issues": 0})
    per_design: dict[str, tuple[float, float]] = {}
    tot = {"issue_reviews": 0, "found": 0, "found_n": 0, "fa": 0, "scored": 0, "sev_exact": 0, "sev_one": 0, "dup": 0, "benign": 0, "info": 0, "control_reviews": 0, "control_fa": 0}
    cls_of = {i["id"]: i["class"] for t in truth.values() for i in t["issues"]}
    for rid, t in sel.items():
        rs = runs.get(rid, [])
        n_issue = len(t["issues"])
        denom_runs = k if count_missing else len(rs)
        per_design[rid] = (sum(len(r["found"]) for r in rs), n_issue * denom_runs)
        for iss in t["issues"]:
            c = by_class[iss["class"]]
            c["issues"] += 1
            hits = [iss["id"] in r["found"] for r in rs]
            c["issue_reviews"] += denom_runs
            c["found"] += sum(hits)
            c["found_in_any"] += int(any(hits))
            c["found_in_all"] += int(len(hits) == k and all(hits))
        for r in rs:
            tot["found"] += len(r["found"])
            tot["fa"] += len(r["false_alarms"])
            tot["scored"] += r["scored_findings"]
            tot["sev_exact"] += r["severity_exact"]
            tot["sev_one"] += r["severity_within_one"]
            tot["dup"] += len(r["duplicates"])
            tot["benign"] += len(r["benign"])
            tot["info"] += r["info_ignored"]
            if t["control"]:
                tot["control_reviews"] += 1
                tot["control_fa"] += len(r["false_alarms"])
        tot["issue_reviews"] += n_issue * denom_runs
    out: dict[str, Any] = {"classes": {}, "overall": {}}
    for c, v in sorted(by_class.items()):
        lo, hi = wilson(v["found"], v["issue_reviews"])
        out["classes"][c] = {**v, "recall": round(v["found"] / v["issue_reviews"], 3) if v["issue_reviews"] else None, "recall_wilson95": [lo, hi]}
    ir = tot["issue_reviews"]
    lo, hi = boot({r: v for r, v in per_design.items() if truth[r]["issues"]}, lambda s: (sum(a for a, _ in s) / sum(b for _, b in s)) if sum(b for _, b in s) else None)
    prec_den = tot["found"] + tot["fa"]
    out["overall"] = {"issue_reviews": ir, "found": tot["found"], "recall": round(tot["found"] / ir, 3) if ir else None, "recall_boot95_over_designs": [lo, hi],
                      "false_alarms": tot["fa"], "precision": round(tot["found"] / prec_den, 3) if prec_den else None,
                      "scored_findings": tot["scored"], "duplicates": tot["dup"], "benign": tot["benign"], "info_ignored": tot["info"],
                      "severity_exact": round(tot["sev_exact"] / tot["found"], 3) if tot["found"] else None,
                      "severity_within_one": round(tot["sev_one"] / tot["found"], 3) if tot["found"] else None,
                      "control_reviews": tot["control_reviews"], "control_false_alarms": tot["control_fa"],
                      "design_reviews": sum(len(r) for r in runs.values())}
    groups = {"verification_environment_defects": [c for c in by_class if c.startswith("tb_")],
              "design_defects": [c for c in by_class if not c.startswith("tb_")]}
    out["groups"] = {}
    for g, cs in groups.items():
        f = sum(by_class[c]["found"] for c in cs)
        n = sum(by_class[c]["issue_reviews"] for c in cs)
        out["groups"][g] = {"classes": sorted(cs), "found": f, "issue_reviews": n, "recall": round(f / n, 3) if n else None, "recall_wilson95": list(wilson(f, n))}
    out["per_design"] = {r: {"found": a, "issue_reviews": b} for r, (a, b) in sorted(per_design.items())}
    return out


def paired(truth, a: dict[str, Any], b: dict[str, Any], k: int) -> dict[str, Any]:
    """Recall of arm a minus arm b per design (designs with planted issues), with a design-level bootstrap interval."""
    ids = [r for r in a["per_design"] if r in b["per_design"] and truth[r]["issues"]]
    d = {}
    for r in ids:
        pa, pb = a["per_design"][r], b["per_design"][r]
        d[r] = (pa["found"] / pa["issue_reviews"] - pb["found"] / pb["issue_reviews"], 1.0) if pa["issue_reviews"] and pb["issue_reviews"] else (0.0, 1.0)
    est = sum(x for x, _ in d.values()) / len(d) if d else None
    lo, hi = boot(d, lambda s: sum(x for x, _ in s) / len(s))
    return {"designs": len(ids), "mean_recall_difference": round(est, 3) if est is not None else None, "boot95": [lo, hi]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--reviews", type=Path, required=True)
    ap.add_argument("--arm", required=True, choices=("agent", "baseline"))
    ap.add_argument("--split", default="heldout", choices=("heldout", "dev", "all"))
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--drop-missing", action="store_true", help="leave not-run reviews out of the denominators (default: they count as missed)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    truth = load_truth(a.truth)
    col = collect(truth, a.reviews, a.arm, a.split, a.k)
    s = summarise(truth, col, a.k, not a.drop_missing)
    s.update({"arm": a.arm, "split": a.split, "k": a.k, "not_run": col["not_run"], "cost": col["cost"], "count_missing": not a.drop_missing})
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"score_{a.arm}_{a.split}.json").write_text(json.dumps(s, indent=1) + "\n")
    # per-review detail stays private: it names issues and findings
    (a.truth / "results").mkdir(exist_ok=True)
    (a.truth / "results" / f"detail_{a.arm}_{a.split}.json").write_text(json.dumps({r: rs for r, rs in col["runs"].items()}, indent=1) + "\n")
    print(json.dumps({"arm": a.arm, "overall": s["overall"], "not_run": len(s["not_run"])}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
