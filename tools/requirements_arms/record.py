#!/usr/bin/env python3
"""Brief 227: copy the records of the arm runs into ``results/227_requirements_readiness/arms/`` and write ``runs.csv`` and ``arms.md``.

    python tools/requirements_arms/record.py --runs runs --out results/227_requirements_readiness/arms

One row per run (arm, design, repeat): did it reach the end of stage 2 at V2 (``gates_pass``), the stop reason, the failure class by a code rule over the stop reason and the
failing gate (a hand check of every failure is recorded in ``failures.md`` by the executor), the independent spec-only bench verdict where it ran, tokens, the plan-cost estimate,
wall time, turns, and for arm B the rounds and questions of the readiness gate. No model scores anything. The design's sources are not copied (only records)."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import sys
from pathlib import Path
from typing import Any

TAG = re.compile(r"^b227_([ABC])_(p\d_\w+?)_r(\d+)$")
FIELDS = ["arm", "design", "run", "run_id", "gates_pass", "reached_stage", "stop", "failure_class", "spectest", "own_checks", "tokens", "plan_cost_usd", "wall_s", "turns",
          "visits_stage2", "rounds", "questions", "answered", "frozen"]


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def classify(stop: str | None, summary: dict[str, Any], spectest: dict[str, Any] | None = None) -> str:
    """The failure class of a run that did not reach the end of stage 2, from the stop reason and the last failing gate (code; the executor checks each by hand).
    Classes: interface, timing, reset, handshake, functional, testbench_wrong, tool, cut_off_reply, budget, requirement_missing (a stop at stage 0 with open questions), and
    spectest_unresolved (the independent bench and the RTL disagree and triage could not say which is wrong)."""
    t = (stop or "").lower()
    if not t:
        return ""
    if t.startswith("requirements:"):
        return "requirement_missing"
    if "spec-test" in t or "spectest" in t:
        sp = spectest or {}
        if sp.get("design_wrong"):
            return "functional"            # the independent bench found the design wrong at least once
        if sp.get("bench_wrong"):
            return "testbench_wrong"       # the triage judged the independent bench wrong every time and the bench could not be repaired
        return "spectest_unresolved"      # the independent spec-only bench and the RTL disagree and triage could not say which is wrong: a requirement reading, the bench or the RTL (hand-labelled later)
    if summary.get("truncated_calls"):
        return "cut_off_reply"
    if "budget" in t or "cost cap" in t or "usd" in t:
        return "budget"
    if "lint" in t or "standards" in t or "design standards" in t:
        return "tool"          # a flow gate (Verilator lint, the coding standard): the design did not meet the flow's rules, not a function failure
    if "simulate" in t or "simulation" in t or "selfcheck" in t or "verification" in t or "assertion" in t:
        return "functional"
    if "timing" in t or "wns" in t:
        return "timing"
    return "tool"


KEEP = ("run_id", "design", "model", "harness", "claude_code_version", "plan_cost_estimate_usd", "stop", "stop_detail", "stages_visited", "loops", "tokens", "turns", "wall_s",
        "truncated_calls", "per_role", "per_stage", "interview", "requirements", "review", "budget_scale")


def trim_summary(s: dict[str, Any]) -> dict[str, Any]:
    """The summary without the interview's question text: that text comes from the pinned private prompts and is never committed (agent/tests/test_99_prompts.py). The counts stay."""
    out = {k: s[k] for k in KEEP if k in s}
    q = s.get("questions") or {}
    out["questions"] = {k: q.get(k) for k in ("asked", "answered", "defaulted", "waived", "unresolved", "level")}
    return out


def one(run: Path, arm: str, design: str, k: int) -> dict[str, Any]:
    d = run / f"b227_{arm}_{design}_r{k}"
    s = json.loads((run / "summary.json").read_text()) if (run / "summary.json").is_file() else {}
    ru = [json.loads(x) for x in (run / "role_usage.jsonl").read_text().splitlines() if x.strip()] if (run / "role_usage.jsonl").is_file() else []
    gates = json.loads((d / "build" / "verif" / "verif_gates.json").read_text()) if (d / "build" / "verif" / "verif_gates.json").is_file() else {}
    rd = json.loads((d / "build" / "requirements" / "readiness.json").read_text()) if (d / "build" / "requirements" / "readiness.json").is_file() else {}
    stop = s.get("stop")
    stages = s.get("stages_visited") or []
    reached2 = 2 in stages and not stop
    own = gates.get("reached")
    spec = ""
    sp = d / "build" / "spectest" / "state.json"
    st: dict[str, Any] = json.loads(sp.read_text()) if sp.is_file() else {}
    if st.get("fired"):
        spec = f"{st.get('outcome')} (bench judged wrong {st.get('bench_wrong', 0)}, design judged wrong {st.get('design_wrong', 0)})"
    gates_pass = reached2 and st.get("outcome") in (None, "passed", "pass", "clean") and not (st.get("fired") and not st.get("passed"))
    rounds = rd.get("rounds") or []
    return {"arm": arm, "design": design, "run": k, "run_id": run.name, "gates_pass": int(bool(gates_pass)), "reached_stage": max(stages) if stages else "", "stop": (stop or "")[:160],
            "failure_class": "" if gates_pass else classify(stop, s, st), "spectest": spec, "own_checks": own or "", "tokens": s.get("tokens"), "plan_cost_usd": s.get("plan_cost_estimate_usd"),
            "wall_s": s.get("wall_s"), "turns": s.get("turns"), "visits_stage2": sum(1 for r in ru if r.get("stage") == "rtl-design-creation" and r.get("role") == "rtl"),
            "rounds": len(rounds) if rd else "", "questions": sum(len(r.get("questions") or []) for r in rounds) if rd else "",
            "answered": sum(sum(bool(q.get("answer")) for q in r.get("questions") or []) for r in rounds) if rd else "", "frozen": int(bool(rd.get("frozen"))) if rd else ""}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", type=Path, default=Path("runs"))
    ap.add_argument("--out", type=Path, default=Path("results/227_requirements_readiness/arms"))
    a = ap.parse_args(argv)
    best: dict[tuple[str, str, int], Path] = {}
    for r in sorted(a.runs.iterdir()):                       # the latest run directory of each tag wins (a re-run replaces an earlier, unscored one)
        for c in r.iterdir() if r.is_dir() else []:
            m = TAG.match(c.name)
            if m:
                best[(m.group(1), m.group(2), int(m.group(3)))] = r
    rows = []
    for (arm, design, k), r in sorted(best.items()):
        row = one(r, arm, design, k)
        rows.append(row)
        dst = a.out / arm / design / f"run{k}"
        dst.mkdir(parents=True, exist_ok=True)
        if (r / "summary.json").is_file():
            (dst / "summary.json").write_text(json.dumps(trim_summary(json.loads((r / "summary.json").read_text())), indent=1) + "\n")
        if (r / "role_usage.jsonl").is_file():
            shutil.copy(r / "role_usage.jsonl", dst / "role_usage.jsonl")
        for rel in ("build/verif/verif_gates.json", "build/requirements/readiness.json", "build/requirements/frozen.json", "build/requirements/state.json",
                    "REQUIREMENTS_REPORT.md", "REQUIREMENTS_READINESS.md", "REQUIREMENTS_NEEDED.md"):
            src = r / f"b227_{arm}_{design}_r{k}" / rel
            if src.is_file():
                shutil.copy(src, dst / Path(rel).name)
    a.out.mkdir(parents=True, exist_ok=True)
    with (a.out / "runs.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} runs recorded in {a.out / 'runs.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
