#!/usr/bin/env python3
"""Run the brief 104 back-test exactly as results/104_strategy_options/preregistration.md says, then score it with flow/options/backtest.py.

    python3 results/104_strategy_options/run_backtest.py run      # nine live runs (Claude Code on the plan), sequential
    python3 results/104_strategy_options/run_backtest.py score    # score the records in backtest/runs/ (no model call) and write backtest/results.json and RESULTS.md

Needs FDA_ACCESS_KEY (.env), the private prompts (FDA_PROMPTS_DIR at the pinned commit) and the claude CLI in the accepted version.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent
BT = HERE / "backtest"
RUNS = BT / "runs"
CASES = {"b96_10g_pre97": ["A", "B"], "c16_montgomery_200mhz": ["A"]}
K = 3
CLI_VERSION = "2.1.321"


def cli_version() -> str:
    return subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()


def run_all() -> int:
    import re
    for case, arms in CASES.items():
        truth = json.loads((BT / "truth" / f"{case}.json").read_text())
        for arm in arms:
            for k in range(1, K + 1):
                d = RUNS / f"{case}__{arm}__{k}"
                if (d / "strategy.json").is_file():
                    continue
                v = cli_version()
                if not v.startswith(CLI_VERSION):
                    print(f"PREFLIGHT_FAIL: claude {v!r} is not {CLI_VERSION}; stopping")
                    return 3
                d.mkdir(parents=True, exist_ok=True)
                cmd = [sys.executable, "-m", "agent", "improve", str(BT / case), truth["request"], "--build-dir", str(BT / case / "evidence"), "--out", str(d), "--json"]
                if arm == "B":
                    cmd.append("--blind")
                t0 = time.time()
                p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800)
                (d / "stdout.json").write_text(p.stdout)
                (d / "stderr.txt").write_text(re.sub(r"(sk-[A-Za-z0-9_\-]{8,})", "<redacted>", p.stderr))
                (d / "meta.json").write_text(json.dumps({"case": case, "arm": arm, "k": k, "exit": p.returncode, "wall_s": round(time.time() - t0, 1), "claude_version": v,
                                                         "time": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=1))
                print(f"{case} {arm} {k}: exit {p.returncode} in {time.time() - t0:.0f}s")
    return 0


def score_all() -> int:
    from flow.options import backtest as B
    res: dict = {"schema": "fda-backtest-results/1", "runs": [], "summary": {}}
    for d in sorted(RUNS.iterdir()) if RUNS.is_dir() else []:
        f = d / "strategy.json"
        if not f.is_file():
            continue
        rec = json.loads(f.read_text())["current"]
        meta = json.loads((d / "meta.json").read_text())
        truth = B.load_truth(BT / "truth" / f"{meta['case']}.json")
        sc = B.score(rec, truth)
        res["runs"].append({"run": d.name, **meta, "attempts": rec["attempts"], "status": rec["status"], "score": sc, "rejected": [{"id": r["id"], "problems": r["problems"]} for r in rec.get("rejected", [])],
                            "notes": rec.get("notes", []), "options_hash": rec.get("options_hash"), "analysis_hash": rec.get("analysis_hash")})
    for case in CASES:
        for arm in CASES[case]:
            rs = [r for r in res["runs"] if r["case"] == case and r["arm"] == arm]
            if not rs:
                continue
            s = {"runs": len(rs), "failed": sum(1 for r in rs if r["status"] != "options"), "found_all_per_run": [r["score"].get("found_all") for r in rs],
                 "in_range_per_run": [r["score"].get("in_range") for r in rs]}
            if case == "b96_10g_pre97":
                s["found_named_per_run"] = [r["score"].get("found_named") for r in rs]
                names = ["agent_cdc", "hand_ref", "agent_both", "all3"]
                s["found_by_variant"] = {n: sum(1 for r in rs if r["score"]["variants"][n]["found"]) for n in names}
                s["in_range_by_variant"] = {n: sum(1 for r in rs if r["score"]["variants"][n].get("in_range")) for n in names}
            res["summary"][f"{case}/{arm}"] = s
    (BT / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(run_all() if (sys.argv[1:] or ["score"])[0] == "run" else score_all())
