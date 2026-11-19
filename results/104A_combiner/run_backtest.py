#!/usr/bin/env python3
"""Run the brief 104A back-test exactly as results/104A_combiner/preregistration.md says, score it with the unchanged flow/options/backtest.py, and publish only structured records.

    python3 results/104A_combiner/run_backtest.py run P1      # nine live runs with the pinned prompts (Claude Code on the plan), sequential
    python3 results/104A_combiner/run_backtest.py run P2      # six live runs with the original prompts of brief 104 (FDA_PROMPTS_DIR must point at the private checkout at 00acde95)
    python3 results/104A_combiner/run_backtest.py publish <kb checkout>   # raw replies -> <kb>/results_private/b104a_combiner/runs/, public record.json + moved_to_kb.json
    python3 results/104A_combiner/run_backtest.py score       # scores backtest/runs/*/record.json (no model call): backtest/results.json and RESULTS.md

Needs FDA_ACCESS_KEY in the environment (the agent's gate), the private prompts, and claude 2.1.321. The fixtures and truth are brief 104's, read in place.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent
OUT = HERE / "backtest"
RUNS = OUT / "runs"
BT104 = ROOT / "results" / "104_strategy_options" / "backtest"
SETS = {"P1": {"b96_10g_pre97": ["A", "B"], "c16_montgomery_200mhz": ["A"]}, "P2": {"b96_10g_pre97": ["A", "B"]}}
K = 3
CLI_VERSION = "2.1.321"
KB_RUNS = "results_private/b104a_combiner/runs"
DROP_OPT = ("approach", "interface_changes", "stage_components", "hidden_components")
DROP_GAIN = ("basis_note", "ceiling_basis")
DROP_RISK = ("summary", "contract_note", "gates")


def cli_version() -> str:
    return subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()


def run_set(name: str) -> int:
    env = dict(os.environ)
    if name == "P2":
        env["FDA_PROMPTS_UNPINNED"] = "1"            # the file-to-manifest check stays; FDA_PROMPTS_DIR is the checkout at the original brief 104 commit
        if not env.get("FDA_PROMPTS_DIR"):
            print("P2 needs FDA_PROMPTS_DIR (private checkout at 00acde95)")
            return 2
    if not env.get("FDA_ACCESS_KEY"):
        print("BLOCKED: FDA_ACCESS_KEY is not set (the agent's access gate)")
        return 2
    for case, arms in SETS[name].items():
        truth = json.loads((BT104 / "truth" / f"{case}.json").read_text())
        for arm in arms:
            for k in range(1, K + 1):
                d = RUNS / f"{name}__{case}__{arm}__{k}"
                if (d / "strategy.json").is_file():
                    continue
                v = cli_version()
                if not v.startswith(CLI_VERSION):
                    print(f"PREFLIGHT_FAIL: claude {v!r} is not {CLI_VERSION}; stopping")
                    return 3
                d.mkdir(parents=True, exist_ok=True)
                cmd = [sys.executable, "-m", "agent", "improve", str(BT104 / case), truth["request"], "--build-dir", str(BT104 / case / "evidence"), "--out", str(d), "--json"]
                if arm == "B":
                    cmd.append("--blind")
                t0 = time.time()
                p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800, env=env)
                (d / "stdout.json").write_text(p.stdout)
                (d / "stderr.txt").write_text(re.sub(r"/home/[^/\s]+", "~", re.sub(r"(sk-[A-Za-z0-9_\-]{8,})", "<redacted>", p.stderr)))
                (d / "meta.json").write_text(json.dumps({"set": name, "case": case, "arm": arm, "k": k, "exit": p.returncode, "wall_s": round(time.time() - t0, 1), "claude_version": v,
                                                         "time": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=1))
                print(f"{name} {case} {arm} {k}: exit {p.returncode} in {time.time() - t0:.0f}s")
    return 0


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def publish(kb: Path) -> int:
    moved: dict = {}
    for d in sorted(RUNS.iterdir()):
        f = d / "strategy.json"
        if not f.is_file():
            continue
        rec = json.loads(f.read_text())["current"]
        pub = {k: v for k, v in rec.items() if k in ("schema", "request", "mode", "blind", "goal", "status", "attempts", "analysis_hash", "analysis_sources", "model", "prompts", "options_hash", "rejected", "combiner")}
        opts = []
        for o in rec.get("options", []):
            q = {k: v for k, v in o.items() if k not in DROP_OPT and k not in ("title", "gain", "risk")}
            q["title_sha256"] = _sha(o["title"])
            q["gain"] = {k: v for k, v in o["gain"].items() if k not in DROP_GAIN}
            q["risk"] = {k: v for k, v in o["risk"].items() if k not in DROP_RISK}
            opts.append(q)
        pub["options"] = opts
        pub["free_text_withheld"] = "title, approach, gain basis notes, gates and risk summaries are in the private repository (moved_to_kb.json)"
        (d / "record.json").write_text(json.dumps(pub, indent=1) + "\n")
        dest = kb / KB_RUNS / d.name
        dest.mkdir(parents=True, exist_ok=True)
        for n in ("strategy.json", "stdout.json", "stderr.txt"):
            src = d / n
            if src.is_file():
                b = src.read_bytes()
                (dest / n).write_bytes(b)
                moved[f"{d.name}/{n}"] = {"kb_path": f"{KB_RUNS}/{d.name}/{n}", "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
                src.unlink()
    (OUT / "moved_to_kb.json").write_text(json.dumps(moved, indent=1) + "\n")
    print(f"published {len(moved)} raw files to {kb / KB_RUNS}")
    return 0


def score_all() -> int:
    from flow.options import backtest as B
    res: dict = {"schema": "fda-backtest-results/1", "runs": [], "summary": {}}
    for d in sorted(RUNS.iterdir()) if RUNS.is_dir() else []:
        f = d / "record.json"
        if not f.is_file():
            continue
        rec = json.loads(f.read_text())
        meta = json.loads((d / "meta.json").read_text())
        truth = B.load_truth(BT104 / "truth" / f"{meta['case']}.json")
        sc = B.score(rec, truth)
        origin = {o["id"]: o.get("origin", "model") for o in rec.get("options", [])}
        for v in (sc.get("variants") or {}).values():
            if v.get("found"):
                v["origin"] = origin.get(v["option"])
        res["runs"].append({"run": d.name, **meta, "attempts": rec["attempts"], "status": rec["status"], "score": sc, "n_model": sum(1 for x in origin.values() if x == "model"),
                            "n_combined": sum(1 for x in origin.values() if x == "combiner"), "rejected": [{"id": r["id"], "problems": r["problems"]} for r in rec.get("rejected", [])],
                            "combiner": rec.get("combiner"), "prompt_system_sha256": rec["prompts"]["system"]["sha256"][:16]})
    keys = sorted({(r["set"], r["case"], r["arm"]) for r in res["runs"]})
    md = ["# Back-test results with the combiner (brief 104A)", "", "Scores are computed by code (`flow/options/backtest.py`, unchanged). P1 = the pinned prompts, P2 = brief 104's original prompts. Counts over three runs.", "",
          "| set / case / arm | failed | model options per run | combined per run | named found (of 3) per run | variants found (of 4) per run | in range per run |", "|---|---|---|---|---|---|---|"]
    for key in keys:
        rs = [r for r in res["runs"] if (r["set"], r["case"], r["arm"]) == key]
        s = {"runs": len(rs), "failed": sum(1 for r in rs if r["status"] != "options"), "n_model": [r["n_model"] for r in rs], "n_combined": [r["n_combined"] for r in rs],
             "found_named": [r["score"].get("found_named") for r in rs], "found_all": [r["score"].get("found_all") for r in rs], "in_range": [r["score"].get("in_range") for r in rs]}
        if key[1] == "b96_10g_pre97":
            names = ["agent_cdc", "hand_ref", "agent_both", "all3"]
            s["found_by_variant"] = {n: sum(1 for r in rs if r["score"]["variants"][n]["found"]) for n in names}
            s["in_range_by_variant"] = {n: sum(1 for r in rs if r["score"]["variants"][n].get("in_range")) for n in names}
            s["over_by_variant"] = {n: [r["score"]["variants"][n].get("over") for r in rs if r["score"]["variants"][n]["found"]] for n in names}
            s["origin_by_variant"] = {n: [r["score"]["variants"][n].get("origin") for r in rs if r["score"]["variants"][n]["found"]] for n in names}
        res["summary"]["/".join(key)] = s
        md.append(f"| {'/'.join(key)} | {s['failed']} | {s['n_model']} | {s['n_combined']} | {s['found_named']} | {s['found_all']} | {s['in_range']} |")
    md += ["", "Per variant (found / in range, of three runs; the range's high end above the measured cut; the origin of the matching option):", ""]
    for k, s in res["summary"].items():
        if "found_by_variant" in s:
            md.append(f"- {k}: " + "; ".join(f"{n} {s['found_by_variant'][n]}/{s['in_range_by_variant'][n]} (over {s['over_by_variant'][n]}, {s['origin_by_variant'][n]})" for n in s["found_by_variant"]))
    (OUT / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    (OUT / "RESULTS.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:] or ["score"]
    sys.exit(run_set(a[1]) if a[0] == "run" else publish(Path(a[1])) if a[0] == "publish" else score_all())
