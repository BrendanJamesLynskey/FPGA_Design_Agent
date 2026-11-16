#!/usr/bin/env python3
"""b82p2 driver (preregistration.md): the agent builds the five development tasks of domain E, 3 repeats each.

    python3 benchmark/v2/runs/b82p2/driver.py run --code <frozen worktree> --bin <dir with the pinned claude> [--tag w1]
    python3 benchmark/v2/runs/b82p2/driver.py table          # results.md, generated from records/*.json only

Each run is one launch of ``python -m agent run`` from the frozen code tree, a hard wall limit, then the task's hidden bench
on the run's rtl/ (benchmark/tools/run_task.py, Icarus; no LLM scores anything), then one record under records/. The
results table is generated from the records.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE / "records"
ART = HERE / "artifacts"
CLAIMS = HERE / "claims"
FROZEN = "b76b4558"
CLI = "2.1.321"
KB = Path("/home/brendan/Claude_sandbox/FPGA_Design_Agent_Knowledge")
USAGE = Path("/home/brendan/Claude_sandbox/_handoff/usage_check.sh")
STOP_PCT = 70
RUN_WALL_S = 3 * 3600
MEM = "5G"
L1 = ["v2_e_cmd_parser", "v2_e_cmd_exec", "v2_e_tlm_pacer", "v2_e_resp_builder"]
L2 = ["v2_e_udp_endpoint"]
TASKS = L1 + L2
LEVEL = {**{t: "L1" for t in L1}, **{t: "L2" for t in L2}}
REPEATS = (1, 2, 3)


def order() -> list[tuple[str, int]]:
    """Phase A repeat-major over the L1 tasks, then phase B."""
    return [(t, r) for r in REPEATS for t in L1] + [(t, r) for r in REPEATS for t in L2]


def rec_path(task: str, rep: int, suffix: str = "") -> Path:
    return REC / f"{task}_r{rep}{suffix}.json"


def records() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(REC.glob("*.json"))] if REC.is_dir() else []


def weekly_pct() -> float:
    out = subprocess.run([str(USAGE)], capture_output=True, text=True, timeout=120).stdout
    m = re.search(r"Current week \(all models\):\s*(\d+)% used", out)
    return float(m.group(1)) if m else 100.0


def headroom_ok() -> tuple[bool, str]:
    load = float(Path("/proc/loadavg").read_text().split()[0])
    avail = next(int(x.split()[1]) for x in Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable"))
    return (load < 6 and avail > 12 * 1024 * 1024), f"load {load}, MemAvailable {avail // 1048576} GiB"


def claim(task: str, rep: int, tag: str) -> bool:
    CLAIMS.mkdir(exist_ok=True)
    d = CLAIMS / f"{task}_r{rep}"
    try:
        d.mkdir()
    except FileExistsError:
        return False
    (d / "owner").write_text(f"{tag} {time.strftime('%F %T')}\n")
    return True


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def preflight(code: Path, binp: Path) -> str | None:
    head = subprocess.run(["git", "-C", str(code), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if not head.startswith(FROZEN):
        return f"code tree HEAD {head[:8]} is not the frozen {FROZEN}"
    dirty = subprocess.run(["git", "-C", str(code), "status", "--porcelain", "--", "agent", "flow", "shell", "benchmark"],
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        return "code tree dirty: " + dirty[:200]
    v = subprocess.run([str(binp / "claude"), "--version"], capture_output=True, text=True).stdout.split()
    if not v or v[0] != CLI:
        return f"claude shim is {v[:1]}, not {CLI}"
    return None


def score(code: Path, task: str, rtl: Path, out: Path) -> dict:
    if not rtl.is_dir() or not any(rtl.glob("*.sv")):
        return {"pass": False, "reason": "no rtl", "tests_passed": 0, "tests": None}
    with open(HERE / "score.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, str(code / "benchmark/tools/run_task.py"), str(code / "benchmark/v2/tasks" / task),
                            "--rtl", str(rtl), "--sim", "icarus", "--json", str(out)], cwd=code, capture_output=True, text=True,
                           timeout=3600)
    try:
        j = json.loads(out.read_text())
    except Exception:
        return {"pass": False, "reason": f"scorer rc {r.returncode}: {(r.stderr or r.stdout)[-300:]}", "tests_passed": 0, "tests": None}
    tests = j.get("tests") or {}
    o = {"pass": bool(j.get("pass")), "tests_passed": sum(1 for v in tests.values() if v is True), "tests": len(tests),
         "failed": sorted(k for k, v in tests.items() if v is not True)}
    if j.get("built") is False:
        o["built"] = False
        o["reason"] = "did not build under the bench: " + str(j.get("error") or "")[-300:]
    return o


def one_run(code: Path, binp: Path, task: str, rep: int, tag: str, retry: int) -> dict:
    td = code / "benchmark/v2/tasks" / task
    runs = code / "runs"
    cmd = ["systemd-run", "--user", "--scope", "-q", "-p", f"MemoryMax={MEM}", "nice", "-n", "10",
           sys.executable, "-m", "agent", "run", str(td / "spec.md"), "--name", task, "--board", "nexys_a7_100t",
           "--interview", "oracle", "--hidden-spec", str(td / "hidden" / "spec.yaml"), "--harness", "claude_code",
           "--cc-model", "claude-sonnet-5-5", "--cc-effort", "medium", "--oracle", "claude_code",
           "--oracle-cc-model", "claude-haiku-5-5", "--review", "off", "--stop-after", "2", "--verif-level", "V2", "--docs", "off"]
    env = {**os.environ, "PATH": f"{binp}:{os.environ['PATH']}", "FDA_KNOWLEDGE": str(KB), "FDA_VIVADO_MAX": "1"}
    t0 = time.time()
    with open(HERE / "launch.lock", "w") as lk:      # one launch at a time until the run directory exists
        fcntl.flock(lk, fcntl.LOCK_EX)
        before = {q.name for q in runs.iterdir()} if runs.is_dir() else set()
        p = subprocess.Popen(cmd, cwd=code, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             start_new_session=True)
        for _ in range(240):
            if runs.is_dir() and {q.name for q in runs.iterdir()} - before:
                break
            time.sleep(0.5)
        new0 = sorted({q.name for q in runs.iterdir()} - before) if runs.is_dir() else []
    hard = False
    try:
        out, _ = p.communicate(timeout=RUN_WALL_S)
    except subprocess.TimeoutExpired:
        hard = True
        os.killpg(p.pid, signal.SIGKILL)          # this run's own process group only
        try:
            out, _ = p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            out = ""
    wall = round(time.time() - t0, 1)
    rid = None
    for n in new0:
        cf = runs / n / "config.json"
        if cf.is_file() and json.loads(cf.read_text()).get("name") == task:
            rid = n
            break
    rec = {"task": task, "level": LEVEL[task], "repeat": rep, "attempt": retry, "run_id": rid, "rc": p.returncode, "wall_s": wall,
           "hard_limit": hard, "worker": tag, "code": FROZEN, "claude_cli": CLI, "started": time.strftime("%F %T", time.localtime(t0))}
    summ = runs / str(rid) / "summary.json" if rid else None
    if summ and summ.is_file():
        s = json.loads(summ.read_text())
        rec.update(tokens=s.get("tokens"), plan_cost_estimate_usd=s.get("plan_cost_estimate_usd"), turns=s.get("turns"),
                   stop=s.get("stop"), stages_visited=s.get("stages_visited"),
                   stage2_visits=sum(1 for n in s.get("stages_visited", []) if n == 2),
                   gates_last=s.get("gates_last"), stage2_gates_passed=bool((s.get("gates_last") or {}).get("rtl-design-creation")),
                   claude_code_version=s.get("claude_code_version"), knowledge_use=s.get("knowledge_use"),
                   questions=s.get("questions"), per_stage=s.get("per_stage"))
    else:
        rec["error_tail"] = (out or "")[-2500:]
        ru = runs / str(rid) / "role_usage.jsonl" if rid else None
        if ru and ru.is_file():
            vs = [json.loads(x) for x in ru.read_text().splitlines() if x.strip()]
            rec["tokens_lower_bound"] = sum(v.get("tokens") or 0 for v in vs)
        rec["stage2_gates_passed"] = False
    first_turn = bool(rid) and (runs / str(rid) / "role_usage.jsonl").is_file()
    rec["reached_first_model_turn"] = first_turn
    if not first_turn and not hard:
        rec["infra_failure"] = "no model turn recorded: " + (out or "")[-300:].replace("\n", " ")
    if rid:
        rd = runs / rid
        design = rd / task
        rec["score"] = score(code, task, design / "rtl", ART / rid / "hidden_score.json")
        sim = [json.loads(x) for x in (design / "build" / "audit.jsonl").read_text().splitlines() if x.strip()] \
            if (design / "build" / "audit.jsonl").is_file() else []
        rec["tool_calls"] = len(sim)
        rec["simulate_calls"] = sum(1 for a in sim if a.get("tool") == "simulate")
        # artifacts: the final RTL, the key logs, and a tarball of the run directory without checkpoints
        a = ART / rid
        a.mkdir(parents=True, exist_ok=True)
        for f in ("summary.json", "config.json", "role_usage.jsonl", "oracle_calls.jsonl"):
            if (rd / f).is_file():
                shutil.copy2(rd / f, a / f)
        if (design / "rtl").is_dir():
            shutil.copytree(design / "rtl", a / "rtl", dirs_exist_ok=True)
        tgz = a / "run_dir.tar.gz"
        with tarfile.open(tgz, "w:gz") as t:
            t.add(rd, arcname=rid, filter=lambda ti: None if any(x in ti.name for x in ("snap.git", "checkpoints.sqlite", "/dcp")) else ti)
        rec["artifact_tarball_sha256"] = sha(tgz)
        rec["artifact_tarball_bytes"] = tgz.stat().st_size
        (a / "driver_stdout_tail.txt").write_text((out or "")[-6000:])
    return rec


def run_all(code: Path, binp: Path, tag: str) -> int:
    for task, rep in order():
        if (HERE / "STOP").exists():
            print("STOP file: no new run", flush=True)
            return 0
        if rec_path(task, rep).exists() or not claim(task, rep, tag):
            continue
        err = preflight(code, binp)
        if err:
            print(f"PREFLIGHT_FAIL: {err}; no run started", flush=True)
            (HERE / "STOP").write_text(f"PREFLIGHT_FAIL {err}\n")
            shutil.rmtree(CLAIMS / f"{task}_r{rep}")
            return 4
        pct = weekly_pct()
        if pct >= STOP_PCT:
            print(f"usage {pct}% >= {STOP_PCT}%: no new launch", flush=True)
            (HERE / "STOP").write_text(f"usage {pct}%\n")
            shutil.rmtree(CLAIMS / f"{task}_r{rep}")
            return 3
        while True:
            ok, why = headroom_ok()
            if ok:
                break
            print(f"waiting: {why}", flush=True)
            time.sleep(60)
        rec = one_run(code, binp, task, rep, tag, 1)
        rec["weekly_pct_before"] = pct
        if rec.get("infra_failure"):
            rec_path(task, rep, "_attempt1_not_run").write_text(json.dumps(rec, indent=1))
            print("infra failure, one labelled re-launch:", rec["infra_failure"][:200], flush=True)
            rec = one_run(code, binp, task, rep, tag, 2)
            rec["weekly_pct_before"] = pct
        rec_path(task, rep).write_text(json.dumps(rec, indent=1))
        print(json.dumps({k: rec.get(k) for k in ("task", "repeat", "run_id", "wall_s", "stop", "score", "infra_failure")}), flush=True)
    return 0


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def table() -> int:
    rs = [r for r in records() if "_attempt1" not in str(r.get("attempt_label", ""))]
    primary = {}
    for p in sorted(REC.glob("*.json")):
        if "_attempt1_not_run" in p.name:
            continue
        r = json.loads(p.read_text())
        primary[(r["task"], r["repeat"])] = r
    md = ["# b82p2 results (generated by `driver.py table` from `records/*.json`; no number is typed by hand)", ""]
    md += ["## Runs", "",
           "| Task | Level | Repeat | Run id | Hidden bench | Tests | Stage-2 gates (agent's own) | Stop | Stage-2 visits | Turns | Wall min | Tokens | Plan-cost est. USD | Not-run attempts |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t, rep in order():
        r = primary.get((t, rep))
        if not r:
            md.append(f"| {t} | {LEVEL[t]} | {rep} | not run | | | | | | | | | | |")
            continue
        sc = r.get("score") or {}
        nr = len(list(REC.glob(f"{t}_r{rep}_attempt1_not_run.json")))
        md.append(f"| {t} | {r['level']} | {rep} | {r.get('run_id')} | {'PASS' if sc.get('pass') else 'fail'} | "
                  f"{sc.get('tests_passed')}/{sc.get('tests')} | {'pass' if r.get('stage2_gates_passed') else 'fail'} | {r.get('stop')} | "
                  f"{r.get('stage2_visits')} | {r.get('turns')} | {round(r['wall_s'] / 60, 1)}{' (hard limit)' if r.get('hard_limit') else ''} | "
                  f"{r.get('tokens', r.get('tokens_lower_bound'))} | {r.get('plan_cost_estimate_usd')} | {nr} |")
    md += ["", "## pass@1 and pass@3 per task (primary: every hidden test passes)", "",
           "| Task | Level | Runs | Passes k | pass@1 = k/n | pass@3 (any of 3) | Gates-clean runs | Escapes (gates clean, hidden fail) |", "|---|---|---|---|---|---|---|---|"]
    tot = {"L1": [0, 0], "L2": [0, 0]}
    per_task = {}
    for t in TASKS:
        rr = [primary[(t, rep)] for rep in REPEATS if (t, rep) in primary]
        k = sum(1 for r in rr if (r.get("score") or {}).get("pass"))
        n = len(rr)
        gc = sum(1 for r in rr if r.get("stage2_gates_passed"))
        esc = sum(1 for r in rr if r.get("stage2_gates_passed") and not (r.get("score") or {}).get("pass"))
        per_task[t] = (k, n)
        tot[LEVEL[t]][0] += k
        tot[LEVEL[t]][1] += n
        md.append(f"| {t} | {LEVEL[t]} | {n} | {k} | {(k / n if n else float('nan')):.2f} | {'yes' if k else ('no' if n else 'n/a')} | {gc}/{n} | {esc} |")
    done = [t for t in TASKS if per_task[t][1]]
    if done:
        p1 = sum(per_task[t][0] / per_task[t][1] for t in done) / len(done)
        p3 = sum(1 for t in done if per_task[t][0]) / len(done)
        md += ["", f"Pooled, tasks as the unit ({len(done)} tasks with runs): pass@1 = {p1:.3f}; pass@3 = {p3:.3f} "
                   f"({sum(1 for t in done if per_task[t][0])} of {len(done)} tasks solved at least once)."]
        for lv in ("L1", "L2"):
            k, n = tot[lv]
            if n:
                lo, hi = wilson(k, n)
                md.append(f"- {lv}: {k} of {n} runs pass; Wilson 95% interval {lo:.2f} to {hi:.2f} (ignores clustering by task).")
        K = sum(v[0] for v in per_task.values())
        N = sum(v[1] for v in per_task.values())
        lo, hi = wilson(K, N)
        md.append(f"- All runs: {K} of {N} pass; Wilson 95% interval {lo:.2f} to {hi:.2f} (ignores clustering by task).")
    cost = [r.get("plan_cost_estimate_usd") for r in primary.values() if r.get("plan_cost_estimate_usd") is not None]
    if cost:
        md += ["", f"Plan-cost estimate (Claude Code's own reported usage, plan-equivalent, not a bill): total {sum(cost):.2f} USD over {len(cost)} runs; "
                   f"median {sorted(cost)[len(cost) // 2]:.2f}; wall total {sum(r['wall_s'] for r in primary.values()) / 3600:.2f} h."]
    (HERE / "results.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "table"])
    ap.add_argument("--code", type=Path)
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--tag", default="w1")
    a = ap.parse_args()
    if a.cmd == "table":
        raise SystemExit(table())
    raise SystemExit(run_all(a.code.resolve(), a.bin.resolve(), a.tag))
