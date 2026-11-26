#!/usr/bin/env python3
"""Brief 227: run the requirements reviewer on the labelled test set (``ids.yaml``) with the Claude Code CLI (plan, not API credit).

    python tools/reviewer_testset/run.py --agentic DEV.jsonl --heldout HELD.jsonl --private DIR --out results.csv --condition kb --runs 2

What is private (never committed): the problem text, the reviewer's replies (``DIR/replies/<condition>/<id>.<run>.json``) and the key file ``DIR/labels_private.yaml``
(for each positive problem, regexes that count as naming the missing fact). What is committed: ``results.csv`` with ids and our outputs only (flag, counts, the
code's decision on naming, tokens), and the scores of ``score.py``. The decision "named the fact" is a regex over the blocking findings' text: no model scores anything.

``--condition kb`` loads the checklist from the knowledge-bank skill (``FDA_KNOWLEDGE``); ``--condition fallback`` uses the public topic list. A run that fails (the plan
limit, a timeout, a reply that is not JSON) is recorded as ``error`` in the private file and is not scored; it is re-run by running the command again.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.graph import readiness as G   # noqa: E402

FIELDS = ["id", "group", "condition", "run", "flagged", "n_blocking", "n_findings", "named", "input_tokens", "output_tokens", "model", "checklist"]


def load_jsonl(path: str | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if path:
        for line in Path(path).read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                out[d["id"]] = d
    return out


def named(keys: list[str], review: dict[str, Any]) -> bool:
    """Any one key regex matches the text (missing fact + question) of a blocking finding. Code only."""
    text = " ".join(f"{f['missing_fact']} {f['question']}" for f in review["findings"] if f["blocking"])
    return any(re.search(k, text) for k in keys)


def run_one(i: str, cond: str, k: int, problems: dict[str, dict[str, Any]], checklist: tuple[str, str], model: str, private: Path, keys: dict[str, list[str]], system: str = "") -> dict[str, Any] | None:
    from agent.models import claude_cli
    rp = private / "replies" / cond / f"{i}.{k}.json"
    if rp.is_file():
        rec = json.loads(rp.read_text())
    else:
        d = problems[i]
        files = d.get("context") or {}
        text = G.problem_text(d["prompt"], files, list((d.get("patch") or {}).keys()))
        user = (f"Request (this is the whole of what the builder receives):\n{text}\n\nRequirements: none are written beyond the request.\n\n"
                f"Checklist:\n{checklist[0]}\n\nDo not give a compliance assessment (leave compliance empty).\n")
        t0 = time.time()
        try:
            res = claude_cli.text_call(system or G.REVIEWER_SYSTEM, user, model=model, effort="medium", timeout_s=900)
        except Exception as e:                                       # a plan limit or a timeout: not scored, re-run later
            (private / "errors.log").open("a").write(f"{time.strftime('%F %T')} {cond} {i} run {k}: {type(e).__name__}: {str(e)[:200]}\n")
            return None
        reply = str(res.get("result", ""))
        if res.get("is_error") or not reply or G.parse_json(reply) is None:
            (private / "errors.log").open("a").write(f"{time.strftime('%F %T')} {cond} {i} run {k}: bad reply: {reply[:120]!r} is_error={res.get('is_error')}\n")
            return None
        u = res.get("usage") or {}
        rec = {"reply": reply, "usage": u, "seconds": round(time.time() - t0, 1), "cost_estimate": res.get("total_cost_usd")}
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(rec))
    rv = G.clean_review(G.parse_json(rec["reply"]) or {})
    u = rec.get("usage") or {}
    nin = int(u.get("input_tokens", 0) or 0) + int(u.get("cache_creation_input_tokens", 0) or 0) + int(u.get("cache_read_input_tokens", 0) or 0)
    return {"id": i, "condition": cond, "run": k, "flagged": int(rv["verdict"] == "not_ready"), "n_blocking": sum(f["blocking"] for f in rv["findings"]), "n_findings": len(rv["findings"]),
            "named": int(named(keys.get(i, []), rv)) if i in keys else 0, "input_tokens": nin, "output_tokens": int(u.get("output_tokens", 0) or 0), "model": model, "checklist": checklist[1]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--agentic", required=True)
    ap.add_argument("--heldout", required=True)
    ap.add_argument("--private", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--ids", default=str(Path(__file__).with_name("ids.yaml")))
    ap.add_argument("--condition", choices=["kb", "fallback"], required=True)
    ap.add_argument("--reviewer", choices=sorted(G.REVIEWERS), default="v1", help="the system prompt: v1 is the pre-registered one; v2 is the post-hoc calibrated one (recorded as condition <cond>_v2)")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--groups", default="A,B,C,D,E,F,G")
    ap.add_argument("--stop-file", type=Path, help="a file whose existence stops the run (the preflight and the usage guard write it)")
    a = ap.parse_args(argv)
    from agent.access import require_or_exit
    require_or_exit("tools/reviewer_testset/run.py")
    ids = yaml.safe_load(Path(a.ids).read_text())
    keys = yaml.safe_load((a.private / "labels_private.yaml").read_text())["keys"]
    problems = {**load_jsonl(a.agentic), **load_jsonl(a.heldout)}
    checklist = G.load_checklist() if a.condition == "kb" else (G.FALLBACK_CHECKLIST, "public fallback checklist")
    if a.condition == "kb" and not checklist[1].startswith(G.KB_SKILL_ID):
        print("the knowledge-bank skill is not at hand (set FDA_KNOWLEDGE): refusing to run the kb condition on the fallback", file=sys.stderr)
        return 2
    cond = a.condition if a.reviewer == "v1" else f"{a.condition}_{a.reviewer}"
    jobs = [(i, g, k) for g in a.groups.split(",") for i in ids["groups"][g]["ids"] for k in range(1, a.runs + 1) if i in problems]
    done = {(r["id"], r["condition"], int(r["run"])) for r in csv.DictReader(a.out.read_text().splitlines())} if a.out.is_file() else set()
    jobs = [j for j in jobs if (j[0], cond, j[2]) not in done]
    gof = {i: g for g, v in ids["groups"].items() for i in v["ids"]}
    new = a.out.is_file() is False
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()

        def work(j):
            if a.stop_file and a.stop_file.exists():
                return None
            return run_one(j[0], cond, j[2], problems, checklist, a.model, a.private, keys, G.REVIEWERS[a.reviewer])
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            for row in ex.map(work, jobs):
                if row is not None:
                    w.writerow({**row, "group": gof[row["id"]]})
                    fh.flush()
    print(f"{len(jobs)} jobs attempted; results in {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
