#!/usr/bin/env python3
"""Brief 42 harness arms, round 1 driver (PREREG.md). One worker; start a second for a second heavy slot.

    python3 results/42_workflows/driver.py run --code <frozen worktree> [--tag w1]     # claims blocks, runs, scores, records
    python3 results/42_workflows/driver.py table                                       # runs.md from runs.jsonl

A block is (seed, task): the four arms A0 / H1 / H2 / H9 run one after another (order rotated by block number), so the
comparison is paired. Blocks are claimed by an atomic mkdir in claims/, so two workers never take the same one. Each run:
``python -m agent run <spec> --stop-after 2 --verif-level V1 --max-usd <cap> --harness-arm <arm>`` from the frozen code tree,
a hard wall-clock limit, then the task's hidden bench on the run's rtl/ (no LLM scores anything), then the record.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "runs.jsonl"
LEDGER = HERE.parents[0] / "spend_ledger.csv"
CLAIMS = HERE / "claims"
FROZEN = HERE / "FROZEN_SHA"

TASKS = {                                   # priority order; all development split or drills outside every split
    "t1_gray_stepper": "benchmark/tasks/t1_gray_stepper",
    "d24_registered_outputs": "benchmark/drills/d24_registered_outputs",
    "t1_debounce_bank": "benchmark/tasks/t1_debounce_bank",
    "d24_no_extra_latency": "benchmark/drills/d24_no_extra_latency",
    "t1_bcd_updown": "benchmark/tasks/t1_bcd_updown",
    "t2_i2c_scanner": "benchmark/tasks/t2_i2c_scanner",
    "t1_lfsr_dice": "benchmark/tasks/t1_lfsr_dice",
    "t1_sync_fifo_regs": "benchmark/tasks/t1_sync_fifo_regs",
}
ARMS = {"A0": "", "H1": "H1", "H2": "H2", "H9": "H9"}
SEEDS = (1, 2, 3)
MODEL = "openai/gpt-6-luna"
RUN_USD = 0.75                              # per-run cap given to the agent
CAP_USD = 60.00                             # brief cap for all harness arms
RUN_WALL_S = 5400                           # hard wall-clock limit per run (90 min)
BRIEF = "42_harness"


def rows() -> list[dict]:
    return [json.loads(x) for x in LOG.read_text().splitlines() if x.strip()] if LOG.exists() else []


ROUND1_TASKS = 4                            # tasks cut, not seeds (brief): the first four of TASKS; the rest only with --extension


def blocks(extension: bool = False) -> list[tuple[int, str]]:
    ts = list(TASKS) if extension else list(TASKS)[:ROUND1_TASKS]
    return [(s, t) for s in SEEDS for t in ts]


def claim(block: tuple[int, str], tag: str) -> bool:
    CLAIMS.mkdir(exist_ok=True)
    d = CLAIMS / f"s{block[0]}_{block[1]}"
    try:
        d.mkdir()
    except FileExistsError:
        return False
    (d / "owner").write_text(f"{tag} {time.strftime('%F %T')}\n")
    return True


def append(path: Path, line: str) -> None:
    with path.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(line)
        fcntl.flock(f, fcntl.LOCK_UN)


def charged(r: dict) -> float:
    """What a run counts against the cap: its provider-reported cost, or the per-run ceiling when a hard kill lost it."""
    return r["cost_usd"] if r.get("cost_usd") is not None else RUN_USD


def spent() -> float:
    return sum(charged(r) for r in rows())


def dead_fda_containers(since: float) -> list[str]:
    """Sandbox containers named fda-<pid>-<hex> whose agent process is gone (ours, after a hard kill)."""
    p = subprocess.run(["docker", "ps", "--filter", "name=fda-", "--format", "{{.Names}}"], capture_output=True, text=True)
    out = []
    for n in p.stdout.split():
        parts = n.split("-")
        if len(parts) >= 3 and parts[1].isdigit() and not Path(f"/proc/{parts[1]}").exists():
            out.append(n)
    return out


def score(root: Path, tdir: str, rtl: Path, out: Path) -> dict:
    if not rtl.is_dir() or not any(rtl.glob("*.sv")):
        return {"pass": False, "reason": "no rtl"}
    with open(HERE / "score.lock", "w") as lk:                # the light scoring lock: one score at a time
        fcntl.flock(lk, fcntl.LOCK_EX)
        out.parent.mkdir(exist_ok=True)
        r = subprocess.run([sys.executable, str(root / "benchmark/tools/run_task.py"), str(root / tdir), "--rtl", str(rtl),
                            "--json", str(out)], cwd=root, capture_output=True, text=True, timeout=3600)
    try:
        j = json.loads(out.read_text())
    except Exception:
        return {"pass": False, "reason": f"scorer rc {r.returncode}: {r.stderr[-300:]}"}
    tests = j.get("tests") or {}
    return {"pass": bool(j.get("pass")), "tests_passed": sum(1 for v in tests.values() if v is True), "tests": len(tests)}


def audit_metrics(design: Path) -> dict:
    """From the run's audit log: simulate calls, hangs (a timed-out or watchdog-ended simulate), tool-call counts."""
    f = design / "build" / "audit.jsonl"
    m = {"simulate_calls": 0, "sim_hangs": 0, "sim_seconds": 0.0, "tool_calls": 0, "refused_unbounded": 0}
    if not f.is_file():
        return m
    for line in f.read_text().splitlines():
        try:
            a = json.loads(line)
        except ValueError:
            continue
        m["tool_calls"] += 1
        if a.get("tool") == "simulate":
            m["simulate_calls"] += 1
            m["sim_seconds"] += a.get("seconds") or 0
            s = a.get("result_summary") or ""
            if "simulation hung" in s or "timed out after" in s:
                m["sim_hangs"] += 1
            if "wait loop with no bound" in s:
                m["refused_unbounded"] += 1
    m["sim_seconds"] = round(m["sim_seconds"], 1)
    off = design / "build" / "tool_results"
    m["offloaded_results"] = len(list(off.glob("*.json"))) if off.is_dir() else 0
    return m


def one_run(root: Path, task: str, seed: int, arm: str, tag: str) -> dict:
    tdir = TASKS[task]
    runs = root / "runs"
    before = {p.name for p in runs.iterdir()} if runs.is_dir() else set()
    cmd = [sys.executable, "-m", "agent", "run", str(root / tdir / "spec.md"), "--name", task, "--stop-after", "2",
           "--verif-level", "V1", "--max-usd", str(RUN_USD), "--model", MODEL]
    if ARMS[arm]:
        cmd += ["--harness-arm", ARMS[arm]]
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    hard = False
    try:
        out, _ = p.communicate(timeout=RUN_WALL_S)
    except subprocess.TimeoutExpired:
        hard = True
        os.killpg(p.pid, signal.SIGKILL)                       # our own run's group only
        try:
            out, _ = p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            out = ""
    wall = round(time.time() - t0, 1)
    if hard:
        for n in dead_fda_containers(t0):
            subprocess.run(["docker", "rm", "-f", n], capture_output=True, timeout=60)
    new = sorted({q.name for q in runs.iterdir()} - before) if runs.is_dir() else []
    rid = next((n for n in new if (runs / n / "config.json").is_file()), None)
    rec = {"task": task, "seed": seed, "arm": arm, "run_id": rid, "rc": p.returncode, "wall_s": wall, "hard_limit": hard,
           "worker": tag}
    summ = runs / str(rid) / "summary.json" if rid else None
    if summ and summ.is_file():
        s = json.loads(summ.read_text())
        st2 = sum(1 for n in s.get("stages_visited", []) if n == 2)
        rec.update(cost_usd=s.get("cost_usd"), tokens=s.get("tokens"), turns=s.get("turns"), stop=s.get("stop"),
                   stage2_visits=st2, stage2_gates_passed=bool((s.get("gates_last") or {}).get("rtl-design-creation")),
                   unreported_cost_calls=s.get("unreported_cost_calls"),
                   per_stage={k: {"tokens": v["tokens"], "cost_usd": v["cost_usd"], "calls": v["calls"]}
                              for k, v in (s.get("per_stage") or {}).items()})
    else:
        rec["error"] = (out or "")[-800:]
        cfg = runs / str(rid) / "config.json" if rid else None
        if cfg and cfg.is_file():                                # a hard-killed run: the meter's last state is not saved
            rec["cost_usd"] = None
    if rid:
        design = runs / rid / task
        rec.update(audit_metrics(design))
        rec["score"] = score(root, tdir, design / "rtl", HERE / "scores" / f"{rid}.json")
    return rec


def run_all(root: Path, tag: str, extension: bool = False) -> int:
    sha = FROZEN.read_text().strip()
    for i, block in enumerate(blocks(extension)):
        if not claim(block, tag):
            continue
        seed, task = block
        order = list(ARMS)
        k = (i + seed) % len(ARMS)
        order = order[k:] + order[:k]                          # rotate the arm order block by block
        for arm in order:
            head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            if head != sha or subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "agent", "flow"],
                                             capture_output=True, text=True).stdout.strip():
                print(f"PREFLIGHT_FAIL: code tree is not the frozen {sha[:8]} (HEAD {head[:8]}); no run started", flush=True)
                return 4
            if spent() + RUN_USD > CAP_USD:
                print(f"cap: spent {spent():.4f}, the next run could pass {CAP_USD}", flush=True)
                return 3
            rec = one_run(root, task, seed, arm, tag)
            append(LOG, json.dumps(rec) + "\n")
            append(LEDGER, f"{time.strftime('%F')},{BRIEF},{rec.get('run_id')},{MODEL},{task}_s{seed}_{arm},,"
                           f"{charged(rec)},"
                           f"\"{'provider-reported' if rec.get('cost_usd') is not None else 'CEILING charged: cost lost to a hard kill'}; "
                           f"deny; stop: {rec.get('stop')}; hard_limit {rec['hard_limit']}\"\n")
            print(json.dumps({k: rec.get(k) for k in ("task", "seed", "arm", "run_id", "wall_s", "cost_usd", "stop", "score")}),
                  flush=True)
            if (HERE / "STOP").exists():
                print("STOP file: finishing after this run", flush=True)
                return 0
    return 0


def table() -> int:
    rs = rows()
    md = ["# Brief 42 harness arms, round 1 (written by driver.py table)", "",
          "Dev split and the two brief 24 drills, deepagents, every role on openai/gpt-6-luna, `--stop-after 2 --verif-level V1`, "
          "per-run cap USD 0.75, hard wall limit 5400 s. Score = the task's hidden bench on the run's rtl/. Cost and tokens are "
          "provider-reported. One row per run.", "",
          "| Task | Seed | Arm | Run | Wall s | Hard limit | Stage-2 visits | Stage-2 gates | Hidden bench | Sim hangs | Tokens | Cost USD | Stop |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rs, key=lambda r: (r["seed"], list(TASKS).index(r["task"]), r["arm"])):
        sc = r.get("score") or {}
        hb = ("pass" if sc.get("pass") else "fail") + (f" {sc['tests_passed']}/{sc['tests']}" if "tests" in sc else f" ({sc.get('reason', 'n/a')})")
        md.append(f"| {r['task']} | {r['seed']} | {r['arm']} | {r.get('run_id')} | {r['wall_s']} | {'yes' if r['hard_limit'] else ''} | "
                  f"{r.get('stage2_visits')} | {'pass' if r.get('stage2_gates_passed') else 'fail'} | {hb} | {r.get('sim_hangs')} | "
                  f"{r.get('tokens')} | {r.get('cost_usd')} | {r.get('stop')} |")
    (HERE / "runs.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "table"])
    ap.add_argument("--code", type=Path)
    ap.add_argument("--tag", default="w1")
    ap.add_argument("--extension", action="store_true", help="also the other four tasks (only after round 1 is complete)")
    a = ap.parse_args()
    if a.cmd == "table":
        raise SystemExit(table())
    raise SystemExit(run_all(a.code.resolve(), a.tag, a.extension))
