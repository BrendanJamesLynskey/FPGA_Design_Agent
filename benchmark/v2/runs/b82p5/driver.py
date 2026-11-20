#!/usr/bin/env python3
"""b82p5 driver (preregistration.md): ONE live run of the UDP endpoint (L2) on the planted spec, to see the derived-constants exit gate fire.

    python3 benchmark/v2/runs/b82p5/driver.py run --code <frozen worktree> --frozen <sha> --bin <dir with the pinned claude>
    python3 benchmark/v2/runs/b82p5/driver.py events         # posthoc/gate_events.json from the run's audit and stage snapshots

The run is one launch of ``python -m agent run`` from the frozen code tree on ``planted/spec.md`` (the 82P3 spec with two planted
wrong constants in its prose), a 4 h hard wall limit, then the task's own hidden bench (the unplanted task directory; it is
scored on the run's rtl/ by benchmark/tools/run_task.py, Icarus; no LLM scores anything), then one record under records/.
"""
from __future__ import annotations

import argparse
import fcntl
import json
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
CLI = "2.1.321"
KB = Path("/home/brendan/Claude_sandbox/_worktrees/82p5-kb")
USAGE = Path("/home/brendan/Claude_sandbox/_handoff/usage_check.sh")
HANDOFF = Path("/home/brendan/Claude_sandbox/_handoff")
STOP_PCT = 88
RUN_WALL_S = 4 * 3600
MEM = "8G"
TASK = "v2_e_udp_endpoint"
PREFIX = "82P5:"


def dotenv_key(code: Path) -> str | None:
    """The access key, read in-process from the code tree's git-ignored .env; never printed or logged."""
    f = code / ".env"
    if f.is_file():
        for ln in f.read_text().splitlines():
            ln = ln.strip()
            if ln.startswith("FDA_ACCESS_KEY="):
                return ln.split("=", 1)[1].strip().strip("\"'")
    return os.environ.get("FDA_ACCESS_KEY")


def take_slot(text: str) -> str:
    while True:
        r = subprocess.run([str(HANDOFF / "take_heavy_slot.sh"), text], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
        print("slot busy, waiting", flush=True)
        time.sleep(60)


def release_slot(lock: str) -> None:
    p = Path(lock)
    if p.is_file() and p.read_text().startswith(PREFIX):      # only a lock whose text is ours
        p.unlink()


def weekly_pct() -> float:
    out = subprocess.run([str(USAGE)], capture_output=True, text=True, timeout=120).stdout
    m = re.search(r"Current week \(all models\):\s*(\d+)% used", out)
    return float(m.group(1)) if m else 100.0


def headroom_ok() -> tuple[bool, str]:
    load = float(Path("/proc/loadavg").read_text().split()[0])
    avail = next(int(x.split()[1]) for x in Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable"))
    return (load < 6 and avail > 12 * 1024 * 1024), f"load {load}, MemAvailable {avail // 1048576} GiB"


def preflight(code: Path, binp: Path, frozen: str) -> str | None:
    head = subprocess.run(["git", "-C", str(code), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if not head.startswith(frozen):
        return f"code tree HEAD {head[:8]} is not the frozen {frozen}"
    dirty = subprocess.run(["git", "-C", str(code), "status", "--porcelain", "--", "agent", "flow", "shell", "benchmark"],
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        return "code tree dirty: " + dirty[:200]
    v = subprocess.run([str(binp / "claude"), "--version"], capture_output=True, text=True).stdout.split()
    if not v or v[0] != CLI:
        return f"claude shim is {v[:1]}, not {CLI}"
    return None


def score(code: Path, rtl: Path, out: Path) -> dict:
    if not rtl.is_dir() or not any(rtl.glob("*.sv")):
        return {"pass": False, "reason": "no rtl", "tests_passed": 0, "tests": None}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    r = subprocess.run([sys.executable, str(code / "benchmark/tools/run_task.py"), str(code / "benchmark/v2/tasks" / TASK),
                        "--rtl", str(rtl), "--sim", "icarus", "--json", str(out)], cwd=code, capture_output=True, text=True, timeout=3600)
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


def run_once(code: Path, binp: Path, frozen: str) -> dict:
    spec = code / "benchmark/v2/runs/b82p5/planted/spec.md"
    td = code / "benchmark/v2/tasks" / TASK
    runs = code / "runs"
    cmd = ["systemd-run", "--user", "--scope", "-q", "-p", f"MemoryMax={MEM}", "nice", "-n", "10",
           sys.executable, "-m", "agent", "run", str(spec), "--name", TASK, "--board", "nexys_a7_100t",
           "--interview", "oracle", "--hidden-spec", str(td / "hidden" / "spec.yaml"), "--harness", "claude_code",
           "--cc-model", "claude-sonnet-5-5", "--cc-effort", "medium", "--oracle", "claude_code",
           "--oracle-cc-model", "claude-haiku-5-5", "--review", "off", "--stop-after", "2", "--verif-level", "V2", "--docs", "off"]
    key = dotenv_key(code)
    env = {**os.environ, "PATH": f"{binp}:{os.environ['PATH']}", "FDA_KNOWLEDGE": str(KB), "FDA_VIVADO_MAX": "1", **({"FDA_ACCESS_KEY": key} if key else {})}
    t0 = time.time()
    before = {q.name for q in runs.iterdir()} if runs.is_dir() else set()
    p = subprocess.Popen(cmd, cwd=code, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
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
        if cf.is_file() and json.loads(cf.read_text()).get("name") == TASK:
            rid = n
            break
    rec = {"task": TASK, "variant": "planted (planted/spec.md)", "level": "L2", "arm": "A", "spec_tests": False, "run_id": rid, "rc": p.returncode,
           "wall_s": wall, "hard_limit": hard, "code": frozen, "claude_cli": CLI, "started": time.strftime("%F %T", time.localtime(t0))}
    summ = runs / str(rid) / "summary.json" if rid else None
    if summ and summ.is_file():
        s = json.loads(summ.read_text())
        rec.update(tokens=s.get("tokens"), plan_cost_estimate_usd=s.get("plan_cost_estimate_usd"), turns=s.get("turns"), stop=s.get("stop"),
                   stages_visited=s.get("stages_visited"), stage2_visits=sum(1 for n in s.get("stages_visited", []) if n == 2),
                   gates_last=s.get("gates_last"), stage2_gates_passed=bool((s.get("gates_last") or {}).get("rtl-design-creation")),
                   clean_stop=s.get("clean_stop"), constants=s.get("constants"), model_table_hash=s.get("model_table_hash"),
                   claude_code_version=s.get("claude_code_version"), questions=s.get("questions"))
    else:
        rec["error_tail"] = (out or "")[-2500:]
        rec["stage2_gates_passed"] = False
    first_turn = bool(rid) and (runs / str(rid) / "role_usage.jsonl").is_file()
    rec["reached_first_model_turn"] = first_turn
    if not first_turn and not hard:
        rec["infra_failure"] = "no model turn recorded: " + (out or "")[-300:].replace("\n", " ")
    if rid:
        rd = runs / rid
        design = rd / TASK
        rec["score"] = score(code, design / "rtl", ART / rid / "hidden_score.json")
        a = ART / rid
        a.mkdir(parents=True, exist_ok=True)
        for f in ("summary.json", "config.json", "role_usage.jsonl", "oracle_calls.jsonl"):
            if (rd / f).is_file():
                shutil.copy2(rd / f, a / f)
        if (design / "rtl").is_dir():
            shutil.copytree(design / "rtl", a / "rtl", dirs_exist_ok=True)
        for f in ("design.xdc", "spec.yaml", "build/derived_constants.json"):
            if (design / f).is_file():
                (a / Path(f).parent.name if "/" in f else a).mkdir(parents=True, exist_ok=True)
                shutil.copy2(design / f, (a / Path(f).parent.name if "/" in f else a) / Path(f).name)
        tgz = a / "run_dir.tar.gz"
        with tarfile.open(tgz, "w:gz") as t:
            t.add(rd, arcname=rid, filter=lambda ti: None if any(x in ti.name for x in ("snap.git", "checkpoints.sqlite", "/dcp")) else ti)
        (a / "driver_stdout_tail.txt").write_text((out or "")[-6000:])
    return rec


def main_run(code: Path, binp: Path, frozen: str) -> int:
    REC.mkdir(exist_ok=True)
    rp = REC / f"{TASK}_planted_A_r1.json"
    if rp.exists():
        print("record exists: the pre-registered run is done; no second run", flush=True)
        return 0
    err = preflight(code, binp, frozen)
    if err:
        print(f"PREFLIGHT_FAIL: {err}; no run started", flush=True)
        return 4
    pct = weekly_pct()
    if pct >= STOP_PCT:
        print(f"usage {pct}% >= {STOP_PCT}%: no launch", flush=True)
        return 3
    while True:
        ok, why = headroom_ok()
        if ok:
            break
        print(f"waiting: {why}", flush=True)
        time.sleep(60)
    lock = take_slot(f"{PREFIX} udp L2 planted run, Vivado synth gate in stage 2 (not impl), start {time.strftime('%H:%M')}, "
                     f"expected end {time.strftime('%H:%M', time.localtime(time.time() + 4 * 3600))}, peak 6G")
    print(f"slot {lock} taken", flush=True)
    try:
        rec = run_once(code, binp, frozen)
    finally:
        release_slot(lock)
    rec["weekly_pct_before"] = pct
    rp.write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: rec.get(k) for k in ("run_id", "wall_s", "stop", "score", "infra_failure")}), flush=True)
    return 0


def events() -> int:
    """The gate's events, read from the run's audit log and the stage snapshots (code tree of the run: runs/<id>)."""
    rec = json.loads(next(REC.glob("*_planted_A_r1.json")).read_text())
    print(json.dumps({k: rec.get(k) for k in ("run_id", "stop", "constants", "score")}, indent=1))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "events"])
    ap.add_argument("--code", type=Path)
    ap.add_argument("--frozen")
    ap.add_argument("--bin", type=Path)
    a = ap.parse_args()
    if a.cmd == "events":
        raise SystemExit(events())
    raise SystemExit(main_run(a.code.resolve(), a.bin.resolve(), a.frozen))
