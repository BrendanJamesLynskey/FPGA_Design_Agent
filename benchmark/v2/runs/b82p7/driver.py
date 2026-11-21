#!/usr/bin/env python3
"""b82p7 driver (preregistration.md): the UDP endpoint (L2), one worker, arm A (spec_tests off) and arm B (on), interleaved, 4 h limit,
each run also scored on its last snapshot before 3 h. Differs from b82p6 in: the frozen tree and knowledge checkout, the "82P7:" slot text,
the weekly-usage stop (97 %), a summary.json written for a run killed at the limit (agent.graph.killed), and a time breakdown per record.

    python3 benchmark/v2/runs/b82p7/driver.py run --code <frozen worktree> --frozen <sha> --bin <dir with the pinned claude> [--tag w1]
    python3 benchmark/v2/runs/b82p7/driver.py table          # results.md, generated from records/*.json only

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
FROZEN = ""          # set from --frozen at start (the code commit of the pre-registration)
CLI = "2.1.321"
KB = Path("/home/brendan/Claude_sandbox/_worktrees/82p7-kb")
USAGE = Path("/home/brendan/Claude_sandbox/_handoff/usage_check.sh")
STOP_PCT = 97
RUN_WALL_S = 4 * 3600          # decision 19: the L2 budget is 4 h for this measurement
MARK_S = 3 * 3600              # every run is also scored on its last snapshot before this mark (comparison with 82P3 and 82P4)
MEM = "8G"
TASK = "v2_e_udp_endpoint"
L1 = []
L2 = [TASK]
TASKS = L2
LEVEL = {TASK: "L2"}
REPEATS = (1, 2, 3)
ARMS = ("A", "B")
HANDOFF = Path("/home/brendan/Claude_sandbox/_handoff")


def order() -> list[tuple[str, int, str]]:
    """Interleaved A, B, A, B, A, B (repeat r of arm A, then repeat r of arm B)."""
    return [(TASK, r, a) for r in REPEATS for a in ARMS]


def rec_path(task: str, rep: int, arm: str, suffix: str = "") -> Path:
    return REC / f"{task}_{arm}_r{rep}{suffix}.json"


def dotenv_key() -> str | None:
    """The access key, read in-process from the code tree's git-ignored .env; never printed or logged."""
    for ln in (FROZEN_TREE / ".env").read_text().splitlines():
        ln = ln.strip()
        if ln.startswith("FDA_ACCESS_KEY="):
            return ln.split("=", 1)[1].strip().strip("\"'")
    return os.environ.get("FDA_ACCESS_KEY")


FROZEN_TREE = Path("/home/brendan/Claude_sandbox/_worktrees/82p7-frozen")


def take_slot(text: str) -> str:
    """Wait (polling every 60 s) until take_heavy_slot.sh admits the job; returns the lock file taken."""
    while True:
        r = subprocess.run([str(HANDOFF / "take_heavy_slot.sh"), text], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
        print("slot busy, waiting", flush=True)
        time.sleep(60)


def release_slot(lock: str) -> None:
    p = Path(lock)
    if p.is_file() and p.read_text().startswith("82P7:"):      # only a lock whose text is ours
        p.unlink()


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


def claim(task: str, rep: int, arm: str, tag: str) -> bool:
    CLAIMS.mkdir(exist_ok=True)
    d = CLAIMS / f"{task}_{arm}_r{rep}"
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
        out.unlink(missing_ok=True)       # review fix: never read a stale score after a scorer crash
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


def one_run(code: Path, binp: Path, task: str, rep: int, arm: str, tag: str, retry: int) -> dict:
    td = code / "benchmark/v2/tasks" / task
    runs = code / "runs"
    cmd = ["systemd-run", "--user", "--scope", "-q", "-p", f"MemoryMax={MEM}", "nice", "-n", "10",
           sys.executable, "-m", "agent", "run", str(td / "spec.md"), "--name", task, "--board", "nexys_a7_100t",
           "--interview", "oracle", "--hidden-spec", str(td / "hidden" / "spec.yaml"), "--harness", "claude_code",
           "--cc-model", "claude-sonnet-5-5", "--cc-effort", "medium", "--oracle", "claude_code",
           "--oracle-cc-model", "claude-haiku-5-5", "--review", "off", "--stop-after", "2", "--verif-level", "V2", "--docs", "off"] + (["--spec-tests"] if arm == "B" else [])
    env = {**os.environ, "PATH": f"{binp}:{os.environ['PATH']}", "FDA_KNOWLEDGE": str(KB), "FDA_VIVADO_MAX": "1", **({"FDA_ACCESS_KEY": dotenv_key()} if dotenv_key() else {})}
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
    if hard and rid:                          # 82P7: a killed run has no summary.json of its own; write one from its run directory
        subprocess.run([sys.executable, "-m", "agent.graph.killed", str(runs / rid), "--wall-limit-s", str(RUN_WALL_S), "--wall-s", str(wall)],
                       cwd=code, capture_output=True, text=True, timeout=300)
    return finish(code, task, rep, arm, tag, retry, rid, p.returncode, wall, hard, t0, out)


def score_at_mark(code: Path, task: str, rd: Path, design: Path, t0: float, wall: float, hard: bool, art: Path, final: dict) -> dict:
    """Pre-registered (decision 19): the hidden score of the last snapshot taken before the 3 h mark (run start + 3 h), so the comparison
    with 82P3 and 82P4 (3 h limit) stays honest. A run that ended on its own before the mark is scored as it ended (its last
    snapshot is its end state); a run still going at the mark is scored from the rtl/ of the newest snap.git commit at or before it."""
    if not hard and wall <= MARK_S:
        return {"basis": "run ended before the 3 h mark; same as the final score", **{k: final.get(k) for k in ("pass", "tests_passed", "tests", "failed")}}
    g = ["git", f"--git-dir={rd / 'snap.git'}"]
    log = subprocess.run(g + ["log", "--all", "--format=%H %ct %s"], capture_output=True, text=True).stdout.splitlines()
    pick = None
    for ln in log:                                              # newest first
        h, ct, subj = (ln.split(" ", 2) + ["", ""])[:3]
        if ct.isdigit() and int(ct) <= t0 + MARK_S:
            pick = (h, int(ct), subj)
            break
    if pick is None:
        return {"basis": "no snapshot before the 3 h mark", "pass": False, "tests_passed": 0, "tests": None}
    tmp = art / "rtl_3h"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    ar = subprocess.run(g + ["archive", pick[0], "rtl"], capture_output=True)
    if ar.returncode == 0:
        subprocess.run(["tar", "-x", "-C", str(tmp)], input=ar.stdout, check=False)
    sc = score(code, task, tmp / "rtl", art / "hidden_score_3h.json")
    return {"basis": "last snapshot before the 3 h mark", "snapshot": pick[0][:12], "snapshot_age_s": round(pick[1] - t0), "snapshot_note": pick[2][:120],
            **{k: sc.get(k) for k in ("pass", "tests_passed", "tests", "failed", "reason")}}


def finish(code: Path, task: str, rep: int, arm: str, tag: str, retry: int, rid: str | None, rc, wall: float, hard: bool, t0: float,
           out: str, reconstructed: bool = False) -> dict:
    runs = code / "runs"
    rec = {"task": task, "level": LEVEL[task], "arm": arm, "repeat": rep, "attempt": retry, "run_id": rid, "rc": rc, "wall_s": wall,
           "hard_limit": hard, "worker": tag, "code": FROZEN, "claude_cli": CLI, "spec_tests": arm == "B", "started": time.strftime("%F %T", time.localtime(t0))}
    if reconstructed:
        rec["reconstructed"] = ("record rebuilt from the finished run directory after the driver's first version failed to write it "
                                "(records/ did not exist); wall = run directory creation to summary.json mtime, rc unknown")
    summ = runs / str(rid) / "summary.json" if rid else None
    if summ and summ.is_file():
        s = json.loads(summ.read_text())
        rec.update(tokens=s.get("tokens"), plan_cost_estimate_usd=s.get("plan_cost_estimate_usd"), turns=s.get("turns"),
                   stop=s.get("stop"), stages_visited=s.get("stages_visited"),
                   stage2_visits=sum(1 for n in s.get("stages_visited", []) if n == 2),
                   gates_last=s.get("gates_last"), stage2_gates_passed=bool((s.get("gates_last") or {}).get("rtl-design-creation")),
                   claude_code_version=s.get("claude_code_version"), knowledge_use=s.get("knowledge_use"),
                   questions=s.get("questions"), per_stage=s.get("per_stage"), spec_test=s.get("spec_test"),
                   clean_stop=s.get("clean_stop"), constants=s.get("constants"), model_table_hash=s.get("model_table_hash"),
                   stop_detail=s.get("stop_detail"), has_last_rtl_message=bool(s.get("last_rtl_message")))
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
        rec["score_3h"] = score_at_mark(code, task, rd, design, t0, wall, hard, ART / rid, rec["score"])
        ev = rd / "routing_events.jsonl"
        rec["routing_events"] = [json.loads(x) for x in ev.read_text().splitlines() if x.strip()] if ev.is_file() else []
        sim = [json.loads(x) for x in (design / "build" / "audit.jsonl").read_text().splitlines() if x.strip()] \
            if (design / "build" / "audit.jsonl").is_file() else []
        gate = [a for a in sim if a.get("tool") == "simulate" and a.get("role") is None]
        rec["time_s"] = {"gate_verilator": round(sum(a.get("seconds") or 0 for a in gate if (a.get("arguments") or {}).get("sim") != "icarus"), 1),
                         "gate_icarus_crosscheck": round(sum(a.get("seconds") or 0 for a in gate if (a.get("arguments") or {}).get("sim") == "icarus"), 1),
                         "icarus_calls": sum(1 for a in gate if (a.get("arguments") or {}).get("sim") == "icarus"),
                         "icarus_timeouts": sum(1 for a in gate if (a.get("arguments") or {}).get("sim") == "icarus" and "timed out" in str(a.get("result_summary"))),
                         "role_simulate": round(sum(a.get("seconds") or 0 for a in sim if a.get("tool") == "simulate" and a.get("role") is not None), 1),
                         "synth_gate_calls": round(sum(a.get("seconds") or 0 for a in sim if a.get("tool") == "build" and a.get("role") is None), 1)}
        rec["tool_calls"] = len(sim)
        rec["simulate_calls"] = sum(1 for a in sim if a.get("tool") == "simulate")
        # artifacts: the final RTL, the key logs, and a tarball of the run directory without checkpoints
        a = ART / rid
        a.mkdir(parents=True, exist_ok=True)
        for f in ("summary.json", "config.json", "role_usage.jsonl", "oracle_calls.jsonl", "routing_events.jsonl"):
            if (rd / f).is_file():
                shutil.copy2(rd / f, a / f)
        if (a / "summary.json").is_file():                        # the RTL role's last message stays in the private archive only
            sj = json.loads((a / "summary.json").read_text())
            if sj.get("last_rtl_message"):
                sj["last_rtl_message"] = {k: v for k, v in sj["last_rtl_message"].items() if k != "text"} | {"text": "in the private run archive"}
            (a / "summary.json").write_text(json.dumps(sj, indent=1))
        if (design / "rtl").is_dir():
            shutil.copytree(design / "rtl", a / "rtl", dirs_exist_ok=True)
        tgz = a / "run_dir.tar.gz"
        with tarfile.open(tgz, "w:gz") as t:
            t.add(rd, arcname=rid, filter=lambda ti: None if any(x in ti.name for x in ("snap.git", "checkpoints.sqlite", "/dcp")) else ti)
        rec["artifact_tarball_sha256"] = sha(tgz)
        rec["artifact_tarball_bytes"] = tgz.stat().st_size
        (a / "driver_stdout_tail.txt").write_text((out or "")[-6000:])
    return rec


def rebuild(code: Path, task: str, rep: int, arm: str, rid: str) -> int:
    """Build the record of a finished run whose record the first driver version failed to write (amendment 1)."""
    REC.mkdir(exist_ok=True)
    rd = code / "runs" / rid
    t0 = time.mktime(time.strptime(rid[:15], "%Y%m%d-%H%M%S"))
    end = (rd / "summary.json").stat().st_mtime
    rec = finish(code, task, rep, arm, "rebuilt", 1, rid, None, round(end - t0, 1), False, t0, "", reconstructed=True)
    rec_path(task, rep, arm).write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: rec.get(k) for k in ("task", "arm", "repeat", "run_id", "wall_s", "stop", "score")}))
    return 0


def run_all(code: Path, binp: Path, tag: str, frozen: str) -> int:
    global FROZEN
    FROZEN = frozen
    REC.mkdir(exist_ok=True)
    for task, rep, arm in order():
        if (HERE / "STOP").exists():
            print("STOP file: no new run", flush=True)
            return 0
        if rec_path(task, rep, arm).exists() or not claim(task, rep, arm, tag):
            continue
        err = preflight(code, binp)
        if err:
            print(f"PREFLIGHT_FAIL: {err}; no run started", flush=True)
            (HERE / "STOP").write_text(f"PREFLIGHT_FAIL {err}\n")
            shutil.rmtree(CLAIMS / f"{task}_{arm}_r{rep}")
            return 4
        pct = weekly_pct()
        if pct >= STOP_PCT:
            print(f"usage {pct}% >= {STOP_PCT}%: no new launch", flush=True)
            (HERE / "STOP").write_text(f"usage {pct}%\n")
            shutil.rmtree(CLAIMS / f"{task}_{arm}_r{rep}")
            return 3
        while True:
            ok, why = headroom_ok()
            if ok:
                break
            print(f"waiting: {why}", flush=True)
            time.sleep(60)
        t = time.strftime("%H:%M")
        lock = take_slot(f"82P7: udp L2 arm {arm} r{rep}, Vivado synth gate in stage 2 (not impl), start {t}, expected end {time.strftime('%H:%M', time.localtime(time.time() + 4 * 3600))}, peak 6G")
        print(f"slot {lock} taken for {arm} r{rep}", flush=True)
        try:
            rec = one_run(code, binp, task, rep, arm, tag, 1)
        finally:
            release_slot(lock)
        rec["weekly_pct_before"] = pct
        rec["weekly_pct_after"] = weekly_pct()
        if rec.get("infra_failure"):
            rec_path(task, rep, arm, "_attempt1_not_run").write_text(json.dumps(rec, indent=1))
            print("infra failure, one labelled re-launch:", rec["infra_failure"][:200], flush=True)
            lock = take_slot(f"82P7: udp L2 arm {arm} r{rep} relaunch, Vivado synth gate, start {time.strftime('%H:%M')}, expected end +4h, peak 6G")
            try:
                rec = one_run(code, binp, task, rep, arm, tag, 2)
            finally:
                release_slot(lock)
            rec["weekly_pct_before"] = pct
            rec["weekly_pct_after"] = weekly_pct()
        rec_path(task, rep, arm).write_text(json.dumps(rec, indent=1))
        print(json.dumps({k: rec.get(k) for k in ("task", "arm", "repeat", "run_id", "wall_s", "stop", "score", "infra_failure")}), flush=True)
    return 0


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def passed(r: dict) -> bool:
    """Review fix: a run killed by the hard wall limit is a budget failure whatever its partial RTL scores."""
    sc = r.get("score") or {}
    return bool(sc.get("pass")) and bool(sc.get("tests")) and sc.get("tests_passed") == sc.get("tests") and not r.get("hard_limit")


def load_old(name: str) -> dict:
    out = {}
    for p in sorted((HERE.parent / name / "records").glob("*.json")):
        if "_attempt1_not_run" not in p.name:
            r = json.loads(p.read_text())
            out[(r["arm"], r["repeat"])] = r
    return out


def stage2_limit_stop(r: dict) -> bool:
    return str(r.get("stop") or "").startswith("stage 2 visited more than")


def spec_bench_reached(r: dict) -> bool:
    st = r.get("spec_test")
    return bool(isinstance(st, dict) and st.get("fired"))


def three_h_rule(r: dict) -> bool:
    """The 82P3/82P4 rule: the run ended on its own within 3 h and every hidden test passed (82P3 and 82P4 killed a run at 3 h)."""
    return passed(r) and r.get("wall_s", 1e9) <= MARK_S


def n_events(r: dict, kind: str) -> int:
    return sum(1 for e in (r.get("routing_events") or []) if e.get("event") == kind)


def clarify_result(r: dict) -> str:
    ev = [e for e in (r.get("routing_events") or []) if e.get("event") == "clarify_constants_check"]
    if not ev:
        return "not recorded"
    return f"{len(ev)} check(s), {sum(1 for e in ev if e.get('failed'))} failed"


def table() -> int:
    primary = {}
    for p in sorted(REC.glob("*.json")):
        if "_attempt1_not_run" in p.name:
            continue
        r = json.loads(p.read_text())
        primary[(r["arm"], r["repeat"])] = r
    old3, old4, old6 = load_old("b82p3"), load_old("b82p4"), load_old("b82p6")
    md = ["# b82p7 results (generated by `driver.py table` from `records/*.json`; no number is typed by hand)", ""]
    md += ["## Runs (4 h limit; also scored on the last snapshot before 3 h)", "",
           "| Arm | Repeat | Run id | 4 h rule | Hidden at end | Hidden at 3 h snapshot | 3 h rule (ended alone within 3 h, all pass) | Own stage-2 gates | Stop | Stage-2 visits | Wall min | Plan-cost est. USD | Usage before to after | P1 hint sent | P1 consequences covered | Clarify-exit check | Owner routing (holders / to spec.yaml owner) | Spec bench fired |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t, rep, arm in order():
        r = primary.get((arm, rep))
        if not r:
            md.append(f"| {arm} | {rep} | not run |" + " |" * 15)
            continue
        sc, s3 = r.get("score") or {}, r.get("score_3h") or {}
        h3 = f"{s3.get('tests_passed')}/{s3.get('tests')}" + ("" if s3.get("basis", "").startswith("last snapshot") else " (run ended before 3 h)" if "ended" in s3.get("basis", "") else f" ({s3.get('basis')})")
        md.append(f"| {arm} | {rep} | {r.get('run_id')} | {'PASS' if passed(r) else 'fail'}{' (killed at 4 h)' if r.get('hard_limit') else ''} | "
                  f"{sc.get('tests_passed')}/{sc.get('tests')} | {h3} | {'PASS' if three_h_rule(r) else 'fail'} | "
                  f"{'pass' if r.get('stage2_gates_passed') else 'fail'} | {r.get('stop')} | {r.get('stage2_visits')} | {round(r['wall_s'] / 60, 1)} | "
                  f"{r.get('plan_cost_estimate_usd')} | {r.get('weekly_pct_before')} to {r.get('weekly_pct_after')} % | "
                  f"{n_events(r, 'p1_hint_sent')} | {n_events(r, 'p1_consequences_covered')} | {clarify_result(r)} | "
                  f"{n_events(r, 'const_id_routed_to_holder')} / {n_events(r, 'const_id_routed_to_spec_yaml_owner')} | {'yes' if spec_bench_reached(r) else 'no'} |")
    md += ["", "## pass@1 (primary: 4 h rule; secondary: 3 h rule). n = 3 per arm decides little.", "",
           "| Group | Runs | 4 h-rule passes | pass@1 | Wilson 95% | 3 h-rule passes | Wilson 95% | Hidden 10/10 at end | Hidden 10/10 at 3 h snapshot | Stage-2 visit-limit stops | Spec bench fired | Cost USD | Wall h |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    groups = [(f"Arm {a} (spec tests {'on' if a == 'B' else 'off'})", [primary[(a, rep)] for rep in REPEATS if (a, rep) in primary]) for a in ARMS]
    groups.append(("Both arms pooled", [r for g in groups for r in g[1]]))
    for name, rr in groups:
        n = len(rr)
        k = sum(1 for r in rr if passed(r))
        k3 = sum(1 for r in rr if three_h_rule(r))
        lo, hi = wilson(k, n)
        lo3, hi3 = wilson(k3, n)
        full = sum(1 for r in rr if (r.get("score") or {}).get("tests") and (r["score"].get("tests_passed") == r["score"]["tests"]))
        full3 = sum(1 for r in rr if (r.get("score_3h") or {}).get("tests") and (r["score_3h"].get("tests_passed") == r["score_3h"]["tests"]))
        lim = sum(1 for r in rr if stage2_limit_stop(r))
        sb = sum(1 for r in rr if spec_bench_reached(r))
        cost = sum(r.get("plan_cost_estimate_usd") or 0 for r in rr)
        wall = sum(r["wall_s"] for r in rr) / 3600
        md.append(f"| {name} | {n} | {k} | {(k / n if n else float('nan')):.2f} | {lo:.2f} to {hi:.2f} | {k3} | {lo3:.2f} to {hi3:.2f} | {full}/{n} | {full3}/{n} | {lim}/{n} | {sb}/{n} | {cost:.2f} | {wall:.2f} |")
    md += ["", "## Where the time went (from `records/*.json` `time_s`, minutes; the 82P6 breakdown is `posthoc/time_table.md`)", "",
           "| Arm | Repeat | Wall | Clean stop | Gate Verilator | Gate Icarus cross-check | Icarus calls (time-outs) | Role's own simulate | Synth gate calls | Cross-check share of wall |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for t, rep, arm in order():
        r = primary.get((arm, rep))
        if not r:
            continue
        ts = r.get("time_s") or {}
        md.append(f"| {arm} | {rep} | {round(r['wall_s'] / 60)} | {'yes' if r.get('clean_stop') else 'no'} | {round(ts.get('gate_verilator', 0) / 60)} | "
                  f"{round(ts.get('gate_icarus_crosscheck', 0) / 60)} | {ts.get('icarus_calls')} ({ts.get('icarus_timeouts')}) | {round(ts.get('role_simulate', 0) / 60)} | "
                  f"{round(ts.get('synth_gate_calls', 0) / 60)} | {ts.get('gate_icarus_crosscheck', 0) / r['wall_s'] * 100:.0f} % |")
    tot_w = sum(r["wall_s"] for r in primary.values())
    tot_c = sum((r.get("time_s") or {}).get("gate_icarus_crosscheck", 0) for r in primary.values())
    md += ["", f"Pooled share of wall time in the Icarus cross-check: {tot_c / tot_w * 100 if tot_w else 0:.0f} % (82P6: 29 %, `posthoc/time_table.md`). "
           f"Clean stops: {sum(1 for r in primary.values() if r.get('clean_stop'))}/{len(primary)}."]
    md += ["", "## Against 82P3 and 82P4 (same task, arms, repeats, scorer and pass rule; their numbers are read from `../b82p3/records/*.json`, `../b82p4/records/*.json` and `../b82p6/records/*.json`; 82P3 and 82P4 had a 3 h limit, 82P6 4 h)", "",
           "| Arm | Repeat | 82P3 hidden, stop | 82P4 hidden, stop | 82P6 hidden at end, stop | 82P7 hidden at end, stop | 82P7 hidden at 3 h snapshot |", "|---|---|---|---|---|---|---|"]

    def cell(r):
        if not r:
            return "not run"
        sc = r.get("score") or {}
        return f"{'PASS' if passed(r) else 'fail'} {sc.get('tests_passed')}/{sc.get('tests')}{' (hard limit)' if r.get('hard_limit') else ''}, {r.get('stop')}"
    for t, rep, arm in order():
        r = primary.get((arm, rep))
        s3 = (r or {}).get("score_3h") or {}
        md.append(f"| {arm} | {rep} | {cell(old3.get((arm, rep)))} | {cell(old4.get((arm, rep)))} | {cell(old6.get((arm, rep)))} | {cell(r)} | {s3.get('tests_passed')}/{s3.get('tests')} |")
    md += ["", "| Set | Runs | Passes (rule of that brief) | pass@1 | Wilson 95% | Stage-2 visit-limit stops |", "|---|---|---|---|---|---|"]
    for name, d, ff in (("82P3", old3, passed), ("82P4", old4, passed), ("82P6 (4 h rule)", old6, passed), ("82P7 (4 h rule)", primary, passed), ("82P7 (3 h rule)", primary, three_h_rule)):
        rr = list(d.values())
        n, k = len(rr), sum(1 for r in rr if ff(r))
        lo, hi = wilson(k, n)
        md.append(f"| {name} | {n} | {k} | {(k / n if n else float('nan')):.2f} | {lo:.2f} to {hi:.2f} | {sum(1 for r in rr if stage2_limit_stop(r))}/{n} |")
    md += ["", "Cost is Claude Code's own reported usage (plan-equivalent, not a bill). A run killed by the hard limit gets its summary.json from `agent.graph.killed` (stop `budget`, cost so far, last state)."]
    (HERE / "results.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "table", "rebuild"])
    ap.add_argument("--task")
    ap.add_argument("--arm", choices=list(ARMS))
    ap.add_argument("--repeat", type=int)
    ap.add_argument("--run-id")
    ap.add_argument("--code", type=Path)
    ap.add_argument("--bin", type=Path)
    ap.add_argument("--frozen")
    ap.add_argument("--tag", default="w1")
    a = ap.parse_args()
    if a.cmd == "table":
        raise SystemExit(table())
    if a.cmd == "rebuild":
        FROZEN = a.frozen or ""
        raise SystemExit(rebuild(a.code.resolve(), a.task, a.repeat, a.arm, a.run_id))
    raise SystemExit(run_all(a.code.resolve(), a.bin.resolve(), a.tag, a.frozen))
