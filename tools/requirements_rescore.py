#!/usr/bin/env python3
"""Re-score recorded runs with the brief 210 risk classes: how many defaulted questions were high risk, and in how many runs a high-risk
default coincided with a failure or a rework. Read only: it reads ``results/**`` of this checkout and, from a git branch, the pilot records
(``git show``; nothing is checked out and nothing is written to the branch).

    python3 tools/requirements_rescore.py [--pilot-ref origin/b209-kr260-pilot] [--pilot-repo <checkout>] --out results/210_requirements

A run is one summary record that holds an interview (``questions.questions``) and its outcome (``stop``/``gates_last``/``loops``), or one pilot
run directory (``design/spec.yaml`` ``resolved_questions`` with ``run_record.json``). The class of each question is the code rules' class
(``agent.graph.requirements.classify``), applied now to the recorded text: none of these runs had a class. A **failure** is a run that did not
stop cleanly (``stop`` is not ``done``, or a pilot run that did not reach stage 9). A **rework** is a run in which a stage was entered more than
once after a failed gate (a loop, a rewind, or a stage visit number above 1). The two are coincidences by run, not causes: the script does not
trace which default led to which failed gate.
"""

from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.graph import requirements as RQ                                 # noqa: E402


def _find(o: Any, depth: int = 0):
    if isinstance(o, dict):
        q = o.get("questions")
        if isinstance(q, dict) and isinstance(q.get("questions"), list) and any(k in o for k in ("stop", "gates_last", "loops")):
            yield o
        if depth < 3:
            for v in o.values():
                yield from _find(v, depth + 1)
    elif isinstance(o, list) and depth < 3:
        for v in o[:60]:
            yield from _find(v, depth + 1)


def main_runs(results: Path) -> list[dict[str, Any]]:
    seen, out = set(), []
    for f in sorted(results.rglob("*.json")):
        if f.stat().st_size > 20_000_000:
            continue
        try:
            d = json.loads(f.read_text())
        except (ValueError, OSError):
            continue
        for s in _find(d):
            key = s.get("run_id") or (str(f), json.dumps(s["questions"].get("questions", [])[:2], sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            qs = [{"text": q.get("text", ""), "status": q.get("status"), "by": q.get("by"), "default": q.get("default", ""), "reason": q.get("reason", "")}
                  for q in s["questions"]["questions"] if isinstance(q, dict)]
            if not qs:
                continue
            stop = str(s.get("stop") or "")
            out.append({"source": "main", "id": str(s.get("run_id") or f.relative_to(results)), "file": str(f.relative_to(ROOT)),
                        "interview": s.get("interview"), "questions": qs, "stop": stop,
                        "failure": stop != "done" and not s.get("clean_stop"),
                        "rework": bool((s.get("loops") or 0) > 0 or s.get("rewinds"))})
    return out


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else ""


def pilot_runs(repo: Path, ref: str) -> list[dict[str, Any]]:
    out = []
    names = _git(repo, "ls-tree", "-r", "--name-only", ref, "pilots/209/").splitlines()
    for spec_path in sorted(n for n in names if n.endswith("/design/spec.yaml")):
        rdir = spec_path[: -len("design/spec.yaml")]
        try:
            spec = yaml.safe_load(_git(repo, "show", f"{ref}:{spec_path}")) or {}
            rec = json.loads(_git(repo, "show", f"{ref}:{rdir}run_record.json"))
        except (ValueError, yaml.YAMLError):
            continue
        qs = [{"text": q.get("question", ""), "status": q.get("status"), "by": q.get("by"), "default": q.get("answer", ""),
               "reason": q.get("default_reason", "")} for q in spec.get("resolved_questions") or [] if isinstance(q, dict)]
        visits = [v for v in rec.get("stage_visits") or [] if isinstance(v, list) and len(v) > 1]
        out.append({"source": "pilot", "id": f"{rec.get('design')}/run{rec.get('run')}", "file": f"{ref}:{rdir}", "interview": "off", "questions": qs,
                    "stop": rec.get("outcome", ""), "failure": not str(rec.get("reached_stage", "")) == "9",
                    "rework": any(isinstance(v[1], int) and v[1] > 1 for v in visits) or bool(rec.get("rewinds"))})
    return out


def score(runs: list[dict[str, Any]]) -> dict[str, Any]:
    per, tot = [], collections.Counter()
    rules = collections.Counter()
    for r in runs:
        c = collections.Counter()
        high_defaults = []
        for q in r["questions"]:
            k = RQ.classify(q["text"], q.get("default", ""), q.get("reason", ""))
            c[("asked", k.cls)] += 1
            if q.get("status") == "defaulted":
                c[("defaulted", k.cls)] += 1
                c[("defaulted", "all")] += 1
                if k.cls == "high":
                    high_defaults.append(k.rule)       # the rule, not the text: some questions are written from private prompt templates
                    rules[k.rule] += 1
        n_def = c[("defaulted", "all")]
        per.append({"id": r["id"], "source": r["source"], "file": r["file"], "interview": r["interview"], "asked": len(r["questions"]),
                    "defaulted": n_def, "defaulted_high": c[("defaulted", "high")], "defaulted_medium": c[("defaulted", "medium")],
                    "defaulted_low": c[("defaulted", "low")], "failure": r["failure"], "rework": r["rework"], "stop": r["stop"][:120],
                    "high_default_rules": dict(collections.Counter(high_defaults))})
        for k, v in c.items():
            tot[k] += v
    runs_with = [p for p in per if p["defaulted_high"]]
    runs_without = [p for p in per if not p["defaulted_high"]]
    rate = lambda ps, f: (sum(1 for p in ps if p[f]), len(ps))               # noqa: E731
    return {"runs": len(per), "questions_asked": sum(tot[("asked", k)] for k in RQ.RISKS),
            "questions_defaulted": tot[("defaulted", "all")],
            "defaulted_by_class": {k: tot[("defaulted", k)] for k in RQ.RISKS},
            "asked_by_class": {k: tot[("asked", k)] for k in RQ.RISKS},
            "runs_with_a_high_default": len(runs_with), "runs_without": len(runs_without),
            "failure_with_high_default": rate(runs_with, "failure"), "failure_without": rate(runs_without, "failure"),
            "rework_with_high_default": rate(runs_with, "rework"), "rework_without": rate(runs_without, "rework"),
            "high_default_rules": dict(rules.most_common()), "per_run": per}


def markdown(res: dict[str, Any], groups: dict[str, dict[str, Any]]) -> str:
    def frac(t):
        return f"{t[0]} of {t[1]}"
    out = ["# Re-scoring recorded runs with the brief 210 risk classes", "",
           "Each recorded question is classed now by `agent.graph.requirements.classify` (none had a class when it ran). A failure is a run that did not "
           "stop cleanly; a rework is a run that re-entered a stage after a failed gate. They are coincidences by run, not causes.", ""]
    out += ["| Group | Runs | Questions asked | Defaulted | Defaulted: high / medium / low | Runs with a high default | Failure (with / without) | Rework (with / without) |",
            "|---|---|---|---|---|---|---|---|"]
    for name, r in groups.items():
        d = r["defaulted_by_class"]
        out.append(f"| {name} | {r['runs']} | {r['questions_asked']} | {r['questions_defaulted']} | {d['high']} / {d['medium']} / {d['low']} | "
                   f"{r['runs_with_a_high_default']} of {r['runs']} | {frac(r['failure_with_high_default'])} / {frac(r['failure_without'])} | "
                   f"{frac(r['rework_with_high_default'])} / {frac(r['rework_without'])} |")
    out += ["", "High-risk defaults by rule: " + ", ".join(f"{k} {v}" for k, v in groups["all"]["high_default_rules"].items()), ""]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--pilot-ref", default="origin/b209-kr260-pilot")
    ap.add_argument("--pilot-repo", default=str(ROOT), help="a checkout that has the pilot ref (read only: git ls-tree and git show)")
    ap.add_argument("--out", default=str(ROOT / "results" / "210_requirements"))
    a = ap.parse_args(argv)
    main_r = main_runs(Path(a.results))
    pil_r = pilot_runs(Path(a.pilot_repo), a.pilot_ref) if a.pilot_ref else []
    groups = {"all": score(main_r + pil_r), "main records (benchmark and development runs)": score(main_r),
              "209 pilot (--interview off)": score(pil_r),
              "oracle-answered main runs": score([r for r in main_r if r["interview"] == "oracle"]),
              "main runs with no interview (off)": score([r for r in main_r if r["interview"] == "off"])}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"pilot_ref": a.pilot_ref, "pilot_head": _git(Path(a.pilot_repo), "rev-parse", a.pilot_ref).strip(),
            "pilot_runs_included": [r["id"] for r in pil_r], "main_run_count": len(main_r)}
    (out / "rescore.json").write_text(json.dumps({"meta": meta, "groups": groups}, indent=1) + "\n")
    (out / "rescore.md").write_text(markdown(groups["all"], groups) + f"\nPilot records: `{a.pilot_ref}` at `{meta['pilot_head'][:12]}`; runs included: "
                                    + ", ".join(meta["pilot_runs_included"]) + ".\n")
    print((out / "rescore.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
