"""Brief 103 stage 2: start and stop agent runs with the CLI's guards, live progress, and locked read-only board actions.

Everything runs against fakes: a fake spawner for runs, a fake transport for the board, a fake runner for the usage check and the heavy-slot script. No test
starts the agent, Vivado or hw_server, and the safety tests prove the board path cannot program or write."""

from __future__ import annotations

import ast
import http.client
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import yaml

from navigator import boardops as B
from navigator import guards as G
from navigator import health as H
from navigator import progress as PG
from navigator import runctl as R
from navigator import server as SV

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "t" * 32
SECRET = "sk-or-v1-PLANTED0123456789abcdef"
MODELS = {"table": [{"name": "rtl", "kind": "claude_code", "model": "claude-sonnet-5-5"}, {"name": "oracle", "kind": "openrouter", "model": "openai/gpt-6-luna"}]}
MODELS_BAD = {"table": MODELS["table"] + [{"name": "bad", "kind": "openrouter", "model": "anthropic/claude-opus-5-5"}]}


class FakeRunner(H.Runner):
    """usage_check.sh appends a line with the percentage in ``self.pct`` (or fails); take_heavy_slot.sh emulates the script's two noclobber slots."""

    def __init__(self, handoff: Path, pct: int = 40, usage_rc: int = 0, stale: bool = False, slots: bool = True):
        self.handoff, self.pct, self.usage_rc, self.stale, self.slots = handoff, pct, usage_rc, stale, slots
        self.calls: list[list[str]] = []

    def run(self, argv, timeout=20, cwd=None, env=None):
        self.calls.append(list(argv))
        if argv[0] == "bash" and argv[1].endswith("usage_check.sh"):
            if self.usage_rc == 0:
                when = "2020-01-01 00:00" if self.stale else time.strftime("%Y-%m-%d %H:%M")
                with open(self.handoff / "usage_log.txt", "a") as f:
                    f.write(f"{when}  Current week (all models): {self.pct}% used · resets Nov 23, 1am;\n")
            return self.usage_rc, "x", ""
        if argv[0] == "bash" and argv[1].endswith("take_heavy_slot.sh"):
            for n in ("heavy_slot.lock", "heavy_slot2.lock"):
                try:
                    with open(self.handoff / n, "x") as f:
                        f.write(argv[2] + "\n")
                    return 0, str(self.handoff / n) + "\n", ""
                except FileExistsError:
                    continue
            return 1, "", ""
        if "models show --json" in " ".join(argv):
            return 0, json.dumps({"purposes": {}, "layers": [], "hash": "h"}), ""
        return 127, "", "not found"


class FakeProc:
    def __init__(self):
        self.pid = 2_000_000_000          # no such process
        self.ev = threading.Event()
        self.code = None

    def wait(self, timeout=None):
        self.ev.wait(timeout)
        return self.code

    def poll(self):
        return self.code

    def finish(self, code=0):
        self.code = code
        self.ev.set()


class FakeSpawner(R.Spawner):
    def __init__(self, fail=False):
        self.calls, self.procs, self.fail = [], [], fail

    def spawn(self, argv, cwd, env, log):
        if self.fail:
            raise OSError("cannot start")
        self.calls.append({"argv": list(argv), "cwd": str(cwd), "log": str(log)})
        p = FakeProc()
        self.procs.append(p)
        return p


class FakeTransport:
    """Records the script; while it runs, board.lock and a heavy slot must be held (the test asserts that); answers from ``self.out``."""

    def __init__(self, handoff: Path, out: str = "", raises: Exception | None = None):
        self.handoff, self.out, self.raises, self.scripts, self.seen_locks = handoff, out, raises, [], []

    def run_tcl(self, tcl, name):
        self.scripts.append(tcl)
        self.seen_locks.append(((self.handoff / "board.lock").is_file(), (self.handoff / "heavy_slot.lock").is_file() or (self.handoff / "heavy_slot2.lock").is_file()))
        if self.raises:
            raise self.raises
        return self.out


KR = "FDA-TARGET Xilinx/XFL1STT4HIMKA localhost:3121/xilinx_tcf/Xilinx/XFL1STT4HIMKA\nFDA-DEVICE Xilinx/XFL1STT4HIMKA xck26_0 xck26 04724093\nFDA-DEVICE Xilinx/XFL1STT4HIMKA arm_dap_1 arm_dap 5ba00477\nFDA-LIST-DONE\n"
SYS_OK = "FDA-SYSMON xck26_0/SYSMON TEMPERATURE=48.3 VCCINT=0.720 VCCAUX=1.801 VCCBRAM=0.851\n"
REGS = "FDA-REG ID 96a00001\nFDA-REG BUILD 1a2b3c4d\nFDA-REG FEATURES 0000007f\nFDA-REG GT_STAT 00000e03\n"


def write_boards(cfg: Path) -> None:
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "boards.yaml").write_text(yaml.safe_dump({"boards": {
        "kr260": {"cable_serial": "XFL1STT4HIMKA", "jtag_uid": "Xilinx/XFL1STT4HIMKA", "part": "xck26", "device": "xck26_0", "power_source": "wall"},
        "nexys_a7_100t": {"cable_serial": "210292AE3B73A", "jtag_uid": "Digilent/210292AE3B73A", "part": "xc7a100t", "device": "xc7a100t_0", "power_source": "wall"}}}))


@pytest.fixture
def env(tmp_path):
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    (handoff / "usage_log.txt").write_text("")
    cfg = tmp_path / "cfg"
    write_boards(cfg)
    return {"tmp": tmp_path, "handoff": handoff, "cfg": cfg, "runs": tmp_path / "runs", "state": tmp_path / "state"}


def make_rc(env, pct=40, spawner=None, **kw):
    runner = FakeRunner(env["handoff"], pct, **{k: kw.pop(k) for k in ("usage_rc", "stale") if k in kw})
    sp = spawner or FakeSpawner()
    rc = R.RunControl(ROOT, env["handoff"], env["runs"], runner, env["state"], lambda: MODELS, spawner=sp, gate=kw.get("gate"), usage_stop=kw.get("usage_stop"))
    return rc, runner, sp


TASK = {"kind": "task", "task": "c10_dds_sine", "board": "nexys_a7_100t", "harness": "claude_code", "model": "claude-haiku-5-5", "effort": "medium", "arms": ["H1"], "max_usd": 2, "confirm": "start"}
PROJ = {"kind": "project", "project": "b102_managed_fcs", "components": ["ctrl"], "request": "shorten the verdict latency", "harness": "claude_code", "model": "claude-sonnet-5-5", "max_usd": 1.5, "confirm": "start"}


def locks_in(env):
    return sorted(p.name for p in env["handoff"].glob("*.lock"))


# --- start: the guards ------------------------------------------------------------------------------------------------------------

def test_start_builds_the_cli_command_and_takes_then_releases_a_slot(env):
    rc, runner, sp = make_rc(env)
    r = rc.start(dict(TASK))
    assert r["started"], r
    argv = sp.calls[0]["argv"]
    assert argv[1:4] == ["-m", "agent", "run"] and argv[4] == "benchmark/course/tasks/c10_dds_sine/spec.md"
    for flag, val in (("--board", "nexys_a7_100t"), ("--harness", "claude_code"), ("--cc-model", "claude-haiku-5-5"), ("--harness-arm", "H1"), ("--max-usd", "2")):
        assert argv[argv.index(flag) + 1] == val
    assert "--allow-fable" not in argv and sp.calls[0]["cwd"] == str(ROOT) and sp.calls[0]["log"].endswith(".log")
    text = (env["handoff"] / "heavy_slot.lock").read_text().strip()
    assert text.startswith("103S2: agent run c10_dds_sine") and "expected end" in text
    assert any("usage_check.sh" in c[1] for c in runner.calls if c[0] == "bash")
    assert rc.records()[0]["status"] == "running"
    sp.procs[0].finish(0)
    for _ in range(100):
        if rc.records()[0]["status"] == "ended":
            break
        time.sleep(0.05)
    rec = rc.records()[0]
    assert rec["status"] == "ended" and rec["exit_code"] == 0 and rec["slot"]["released"] is True
    assert locks_in(env) == []


def test_project_resume_command_uses_the_agents_scope_resolution(env):
    rc, _, sp = make_rc(env)
    assert rc.start(dict(PROJ))["started"]
    argv = sp.calls[0]["argv"]
    assert argv[3:6] == ["resume", "designs/b102_managed_fcs", "shorten the verdict latency"] and argv[argv.index("--scope") + 1] == "ctrl" and "--harness-arm" not in argv
    sp.procs[0].finish(1)


@pytest.mark.parametrize("pct,rc_,stale,why", [(90, 0, False, "at or above"), (97, 0, False, "at or above"), (10, 1, False, "failed"), (10, 0, True, "old")])
def test_usage_guard_refuses_and_starts_nothing(env, pct, rc_, stale, why):
    rc, _, sp = make_rc(env, pct=pct, usage_rc=rc_, stale=stale)
    r = rc.start(dict(TASK))
    assert r["started"] is False and why in r["refused"]
    assert sp.calls == [] and locks_in(env) == []


def test_usage_just_below_the_stop_starts(env):
    rc, _, sp = make_rc(env, pct=89)
    assert rc.start(dict(TASK))["started"]
    sp.procs[0].finish()


def test_no_heavy_slot_refuses_and_leaves_the_other_locks_alone(env):
    (env["handoff"] / "heavy_slot.lock").write_text("other: job\n")
    (env["handoff"] / "heavy_slot2.lock").write_text("other2: job\n")
    rc, _, sp = make_rc(env)
    r = rc.start(dict(TASK))
    assert r["started"] is False and "heavy slot" in r["refused"] and sp.calls == []
    assert (env["handoff"] / "heavy_slot.lock").read_text() == "other: job\n" and (env["handoff"] / "heavy_slot2.lock").read_text() == "other2: job\n"


def test_spawn_failure_releases_the_slot(env):
    rc, _, sp = make_rc(env, spawner=FakeSpawner(fail=True))
    with pytest.raises(OSError):
        rc.start(dict(TASK))
    assert locks_in(env) == []


def test_slot_of_another_session_is_never_released(env):
    rc, _, sp = make_rc(env)
    assert rc.start(dict(TASK))["started"]
    (env["handoff"] / "heavy_slot.lock").write_text("someone else: took it over\n")          # the lock now holds another text
    sp.procs[0].finish(0)
    for _ in range(100):
        if rc.records()[0]["status"] == "ended":
            break
        time.sleep(0.05)
    assert rc.records()[0]["slot"]["released"] is False
    assert (env["handoff"] / "heavy_slot.lock").read_text() == "someone else: took it over\n"


def test_one_navigator_run_at_a_time(env):
    rc, _, sp = make_rc(env)
    assert rc.start(dict(TASK))["started"]
    r = rc.start(dict(TASK))
    assert r["started"] is False and "one at a time" in r["refused"] and len(sp.calls) == 1
    sp.procs[0].finish()


@pytest.mark.parametrize("patch,why", [
    ({"confirm": None}, "confirmation"), ({"model": "claude-fable-5"}, "never"), ({"model": "claude-opus-5-5"}, "never"), ({"harness": "deepagents", "model": "anthropic/claude-opus-5-5"}, "never"),
    ({"harness": "deepagents", "model": "claude-haiku-5-5"}, "not one the resolved table"), ({"model": "not-in-table"}, "not one the resolved table"), ({"model": "x; rm -rf /"}, "pick a model"),
    ({"task": "../../etc/passwd"}, "task from the list"), ({"task": "c10_dds_sine/../../x"}, "task from the list"), ({"board": "../x"}, "board"), ({"max_usd": 11}, "budget"), ({"max_usd": 0}, "budget"),
    ({"max_usd": True}, "budget"), ({"max_usd": "3"}, "budget"), ({"arms": ["H1;x"]}, "arms"), ({"effort": "ultra"}, "effort"), ({"kind": "shell"}, "kind"), ({"harness": "x"}, "harness")])
def test_field_checks_refuse(env, patch, why):
    rc, _, sp = make_rc(env)
    r = rc.start({**TASK, **patch})
    assert r["started"] is False and why in r["refused"], r
    assert sp.calls == [] and locks_in(env) == []


@pytest.mark.parametrize("patch,why", [({"request": "-rf"}, "cannot start with"), ({"request": ""}, "write the change request"), ({"project": "../x"}, "managed project"),
                                       ({"components": ["crc"]}, "agent would ask"), ({"components": ["../x"]}, "component names"), ({"components": "ctrl"}, "component names")])
def test_project_field_checks_refuse(env, patch, why):
    rc, _, sp = make_rc(env)
    r = rc.start({**PROJ, **patch})
    assert r["started"] is False and why in r["refused"], r
    assert sp.calls == [] and locks_in(env) == []


def test_access_gate_is_checked_before_a_start(env):
    from agent.access import AccessDenied

    def gate(e):
        raise AccessDenied("access key required")
    rc, _, sp = make_rc(env, gate=gate)
    r = rc.start(dict(TASK))
    assert r["started"] is False and "access gate" in r["refused"] and sp.calls == []


def test_a_task_the_course_does_not_list_and_the_held_out_sets_are_not_offered(env):
    rc, _, _ = make_rc(env)
    t = rc.tasks()
    assert "c10_dds_sine" in t and all("benchmark_private" not in str(p) and "eval1" not in str(p) for p in t.values())
    assert all(str(p).startswith(str(ROOT / "benchmark" / "course" / "tasks")) for p in t.values())


def test_the_model_offer_excludes_fable_and_opus(env):
    rc, _, _ = make_rc(env)
    rc.models_view = lambda: MODELS_BAD
    m = rc.allowed_models()
    assert "claude-sonnet-5-5" in m["claude_code"] and "openai/gpt-6-luna" in m["deepagents"]
    assert not any(re.search("fable|opus|anthropic/", x, re.I) for v in m.values() for x in v)


# --- stop: its own process group only ----------------------------------------------------------------------------------------------

class SleepControl(R.RunControl):
    def build(self, p):
        return [sys.executable, "-c", "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); time.sleep(60)"], {"kind": "task", "target": "c10_dds_sine"}


def test_stop_signals_only_the_runs_own_process_group(env):
    runner = FakeRunner(env["handoff"])
    rc = SleepControl(ROOT, env["handoff"], env["runs"], runner, env["state"], lambda: MODELS)
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    try:
        r = rc.start({"confirm": "start"})
        assert r["started"], r
        sid = r["id"]
        rec = rc.recs[sid]
        assert rec["pid"] == rec["pgid"] and rec["pgid"] != os.getpgid(0)
        assert rc.stop("n-19990101-000000-abcd")["stopped"] is False and rc.stop("../x")["stopped"] is False and rc.stop(None)["stopped"] is False
        st = rc.stop(sid)
        assert st["stopped"] is True
        for _ in range(100):
            if rc.records()[0]["status"] == "ended":
                break
            time.sleep(0.1)
        assert rc.records()[0]["status"] == "ended" and rc.records()[0]["slot"]["released"] is True and locks_in(env) == []
        assert bystander.poll() is None, "a process outside the run's group was signalled"
        assert rc.stop(sid)["stopped"] is False
    finally:
        bystander.kill()
        bystander.wait()
        for sid, r in rc.recs.items():
            if r["status"] == "running":
                os.killpg(r["pgid"], signal.SIGKILL)


def test_stop_refuses_a_pid_that_is_not_the_recorded_process(env):
    rc, _, sp = make_rc(env)
    assert rc.start(dict(TASK))["started"]
    sid = next(iter(rc.recs))
    sent = []
    rc.killpg = lambda pg, sig: sent.append((pg, sig))
    assert rc.stop(sid)["stopped"] is False and sent == []                  # the fake pid does not exist: nothing is signalled
    sp.procs[0].finish()


def test_reconcile_releases_the_slot_of_a_run_that_is_gone(env):
    rc, _, sp = make_rc(env)
    assert rc.start(dict(TASK))["started"]
    sid = next(iter(rc.recs))
    rc.procs.clear()
    sp.procs[0].finish()
    time.sleep(0.2)
    assert rc.recs[sid]["status"] == "ended"
    # a record left 'running' by a navigator that was killed: a new one finds the process gone and releases its slot
    (env["handoff"] / "heavy_slot.lock").write_text(rc.recs[sid]["slot_text"] + "\n")
    rc.recs[sid].update(status="running", pid=2_000_000_001, starttime=5)
    rc._save()
    rc2, _, _ = make_rc(env)
    rc2.reconcile()
    assert rc2.recs[sid]["status"] == "ended" and rc2.recs[sid]["slot_released"] is True and locks_in(env) == []


# --- live progress -----------------------------------------------------------------------------------------------------------------

def make_run(runs: Path, name="20261120-100000-abcd", finished=False, secret=False):
    d = runs / name
    (d / "des" / "build").mkdir(parents=True)
    (d / "config.json").write_text(json.dumps({"name": "des", "harness": "claude_code", "cc_model": "claude-sonnet-5-5", "run_limits": {"usd": 3.0, "turns": 300}}))
    (d / "role_usage.jsonl").write_text("\n".join(json.dumps(x) for x in (
        {"stage": "clarify", "visit": 1, "role": "clarify", "tokens": 100, "plan_cost_estimate_usd": 0.05},
        {"stage": "rtl-design-creation", "visit": 1, "role": "rtl", "tokens": 400, "plan_cost_estimate_usd": 0.2},
        {"stage": "rtl-design-creation", "visit": 2, "role": "rtl", "tokens": 300, "plan_cost_estimate_usd": 0.1})) + "\n")
    (d / "trace.jsonl").write_text("\n".join(json.dumps(x) for x in (
        {"kind": "model", "cost_usd": 0.25, "stage": "clarify"}, {"kind": "model", "cost_usd": "unreported", "stage": "rtl-design-creation"}, {"kind": "tool", "tool": "lint", "stage": "rtl-design-creation"})) + "\n")
    (d / "snapshots.json").write_text(json.dumps([{"n": 0, "stage": "clarify", "commit": "x"}]))
    gates = "gates: des_top (base): FAIL  WNS -0.2 ns\n  rtl: pass\n    ok   rtl_lint\n  post_synth: FAIL\n    FAIL post_synth_timing\n"
    rows = [{"t": 1.0, "tool": "lint", "stage": "rtl-design-creation", "ok": True, "refused": False, "result_summary": "lint: clean\nmore"},
            {"t": 2.0, "tool": "gates", "stage": "rtl-design-creation", "ok": True, "refused": False, "result_summary": gates},
            {"t": 3.0, "tool": "read_file", "stage": "rtl-design-creation", "ok": False, "refused": True, "result_summary": f"<img src=x onerror=alert(1)> {SECRET}" if secret else "refused"}]
    (d / "des" / "build" / "audit.jsonl").write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    if finished:
        (d / "summary.json").write_text(json.dumps({"stop": "done"}))
    return d


def test_progress_reads_stage_visit_cost_gates_and_audit_tail(tmp_path):
    runs = tmp_path / "runs"
    make_run(runs)
    p = PG.run_progress(runs, "20261120-100000-abcd")
    assert p["status"] == "active" and p["stage"] == "rtl-design-creation" and p["stage_n"] == 2 and p["visit"] == 2 and p["visits"] == {"clarify": 1, "rtl-design-creation": 2}
    assert p["cost"]["reported_usd"] == 0.25 and p["cost"]["reported_calls_without_cost"] == 1 and p["cost"]["plan_estimate_usd"] == 0.35 and p["cost"]["budget_usd"] == 3.0
    assert p["tokens"] == 800 and p["stages_done"] == [{"n": 0, "stage": "clarify"}]
    g = p["gates"][0]
    assert g["verdict"] == "FAIL" and g["variant"] == "base" and g["stages"] == {"rtl": "pass", "post_synth": "fail"} and g["failing"] == ["post_synth: post_synth_timing"]
    assert [a["tool"] for a in p["audit_tail"]] == ["lint", "gates", "read_file"] and p["audit_tail"][0]["line"] == "lint: clean" and p["audit_tail"][2]["refused"] is True


def test_progress_status_finished_idle_and_bad_ids(tmp_path):
    runs = tmp_path / "runs"
    make_run(runs, "20261120-100000-aaaa", finished=True)
    old = make_run(runs, "20261120-100000-bbbb")
    for f in old.rglob("*"):
        if f.is_file():
            os.utime(f, (time.time() - 3600, time.time() - 3600))
    assert PG.run_progress(runs, "20261120-100000-aaaa")["status"] == "finished"
    assert PG.run_progress(runs, "20261120-100000-aaaa")["stop"] == "done"
    assert PG.run_progress(runs, "20261120-100000-bbbb")["status"] == "idle"
    for bad in ("../x", "..", "a/b", "", "x" * 200, ".hidden"):
        assert PG.run_progress(runs, bad) is None
    assert [r["id"] for r in PG.live_list(runs)] == ["20261120-100000-bbbb", "20261120-100000-aaaa"]


REAL_RUNS = Path("/home/brendan/Claude_sandbox/FPGA_Design_Agent/runs")


@pytest.mark.skipif(not REAL_RUNS.is_dir(), reason="no CLI run directory on this machine")
def test_progress_reads_runs_started_from_the_command_line():
    done = [r for r in PG.run_ids(REAL_RUNS, 60) if (REAL_RUNS / r / "audit_probe").exists() or (REAL_RUNS / r / "trace.jsonl").is_file()]
    assert done, "no CLI run with a trace found"
    p = PG.run_progress(REAL_RUNS, done[0])
    assert p["stage"] in p["stages"] and p["audit_rows"] > 0 and p["cost"]["budget_usd"] is not None and p["audit_tail"]
    assert any(g["verdict"] in ("PASS", "FAIL") for r in done[:6] for g in PG.run_progress(REAL_RUNS, r)["gates"]), "no gate result parsed from the real audit logs"


# --- board actions -----------------------------------------------------------------------------------------------------------------

def make_ops(env, out="", raises=None, pct=40, slots=True):
    tr = FakeTransport(env["handoff"], out, raises)
    return B.BoardOps(env["handoff"], FakeRunner(env["handoff"], pct), env["cfg"], tr), tr


def test_all_four_reads_decode_and_hold_both_locks_only_while_running(env):
    ops, tr = make_ops(env, KR + SYS_OK + REGS)
    r = ops.run("kr260", "all")
    assert r["ok"] is True and tr.seen_locks == [(True, True)]
    assert locks_in(env) == [] and r["locks"]["released"] == {"slot": True, "board_lock": True}
    assert r["targets"][0]["mine"] is True and r["targets"][0]["devices"][0]["part"] == "xck26" and "XFL1STT4HIMKA" not in json.dumps(r)
    assert r["sysmon"]["verdict"] == "inside ROC" and {c["name"] for c in r["sysmon"]["channels"]} == {"TEMPERATURE", "VCCINT", "VCCAUX", "VCCBRAM"}
    assert r["design"]["id"] == "0x96A00001" and "b96_kr260_10g" in r["design"]["design"] and r["design"]["build_stamp"] == "0x1A2B3C4D"
    assert r["design"]["features_set"] == ["ALWAYS_1", "NEAR_END", "TRADE", "RATE_MATCH", "EYESCAN", "RM_OWN", "GT_BYPASS"]
    assert r["link"]["link_up"] is True and r["link"]["bits"]["pcs_lock"] == 1 and r["link"]["bits"]["mod_abs"] == 1


def test_sysmon_outside_roc_is_reported_per_channel(env):
    ops, _ = make_ops(env, "FDA-SYSMON x TEMPERATURE=91.0 VCCINT=0.720 VCCAUX=1.801 VCCBRAM=0.851\n")
    r = ops.run("kr260", "sysmon")
    assert r["sysmon"]["verdict"] == "outside ROC" and [c["name"] for c in r["sysmon"]["channels"] if not c["inside"]] == ["TEMPERATURE"]
    assert "DS925" in r["sysmon"]["roc_source"] and "droop" in r["sysmon"]["caveat"]


def test_a_board_without_a_register_profile_gets_targets_and_sysmon_only(env):
    ops, tr = make_ops(env, "FDA-SYSMON x TEMPERATURE=40 VCCINT=1.0 VCCAUX=1.8 VCCBRAM=1.0\n")
    r = ops.run("nexys_a7_100t", "design_id")
    assert r["ok"] is False and "no register profile" in r["refused"] and tr.scripts == [] and locks_in(env) == []
    r = ops.run("nexys_a7_100t", "sysmon")
    assert r["sysmon"]["verdict"] == "inside ROC" and "DS181" in r["sysmon"]["roc_source"]
    lst = {b["board"]: b for b in ops.listing()["boards"]}
    assert lst["nexys_a7_100t"]["actions"] == ["jtag_targets", "sysmon"] and "all" in lst["kr260"]["actions"] and "XFL1" not in json.dumps(lst)


def test_marker_error_is_reported_not_guessed(env):
    ops, _ = make_ops(env, "FDA-ERR regs no 0x58A0 marker in the captured data (00): the loaded design has no such register bus\n")
    r = ops.run("kr260", "design_id")
    assert r["ok"] is False and r["section_errors"][0]["what"].startswith("no 0x58A0 marker") and r["design"] == {}


def test_board_lock_held_refuses_and_leaves_it_alone(env):
    (env["handoff"] / "board.lock").write_text("96F: soak, 2026-11-20 12:00, expected end 14:00\n")
    ops, tr = make_ops(env, KR)
    r = ops.run("kr260", "jtag_targets")
    assert r["ok"] is False and "board lock is held" in r["refused"] and "96F" in r["refused"] and tr.scripts == []
    assert (env["handoff"] / "board.lock").read_text() == "96F: soak, 2026-11-20 12:00, expected end 14:00\n" and locks_in(env) == ["board.lock"]


def test_no_heavy_slot_releases_the_board_lock_it_took(env):
    (env["handoff"] / "heavy_slot.lock").write_text("a: x\n")
    (env["handoff"] / "heavy_slot2.lock").write_text("b: y\n")
    ops, tr = make_ops(env, KR)
    r = ops.run("kr260", "jtag_targets")
    assert "no heavy slot" in r["refused"] and tr.scripts == []
    assert locks_in(env) == ["heavy_slot.lock", "heavy_slot2.lock"]


@pytest.mark.parametrize("exc", [RuntimeError("vivado exploded"), B.BoardRefused("Vivado did not finish within 240 s"), KeyboardInterrupt])
def test_locks_are_released_on_every_error_path(env, exc):
    ops, tr = make_ops(env, "", raises=exc)
    try:
        r = ops.run("kr260", "sysmon")
        assert r["ok"] is False and "error" in r
    except KeyboardInterrupt:
        pass
    assert tr.seen_locks == [(True, True)] and locks_in(env) == []


def test_a_lock_changed_by_someone_else_during_the_run_is_not_removed(env):
    class Hijack(FakeTransport):
        def run_tcl(self, tcl, name):
            (self.handoff / "board.lock").write_text("other: took the board over\n")
            return super().run_tcl(tcl, name)
    tr = Hijack(env["handoff"], KR)
    ops = B.BoardOps(env["handoff"], FakeRunner(env["handoff"]), env["cfg"], tr)
    r = ops.run("kr260", "jtag_targets")
    assert r["locks"]["released"] == {"slot": True, "board_lock": False}
    assert (env["handoff"] / "board.lock").read_text() == "other: took the board over\n"


@pytest.mark.parametrize("board,action", [("../etc", "all"), ("kr260", "program"), ("kr260", "../all"), (None, "all"), ("kr260", None), ("nope", "all"), ("kr260;x", "all")])
def test_unknown_board_or_action_is_refused_before_any_lock(env, board, action):
    ops, tr = make_ops(env, KR)
    r = ops.run(board, action)
    assert r["ok"] is False and r["refused"] and tr.scripts == [] and locks_in(env) == []


def test_bad_serial_or_device_in_boards_file_is_refused(env):
    (env["cfg"] / "boards.yaml").write_text(yaml.safe_dump({"boards": {"kr260": {"jtag_uid": "Xilinx/X$(reboot)", "part": "xck26", "device": "xck26_0"}, "b2": {"jtag_uid": "Xilinx/ABCD1234", "part": "xck26", "device": "d; exit"}}}))
    ops, tr = make_ops(env, KR)
    assert "no usable jtag_uid" in ops.run("kr260", "sysmon")["refused"] and "no usable jtag_uid" in ops.run("b2", "sysmon")["refused"] and tr.scripts == []


# --- the safety proof: no navigator path can program or write -------------------------------------------------------------------------

FORBIDDEN_WORDS = ("program_hw_devices", "program_hw_cfgmem", "create_hw_cfgmem", "set_property", "write_hw", "b58a_wr", "b96_wr", "b96_laser", "run_hw", "boot_hw", "commit_hw", "erase", "efuse", "bbram", "tx_disable",
                   "source ", "exec ", "flash", "laser")


def all_scripts():
    prof = B.PROFILES["kr260"]
    for action in B.ACTIONS:
        for uid, dev, pr in (("Xilinx/XFL1STT4HIMKA", "xck26_0", prof), ("Digilent/210292AE3B73A", "xc7a100t_0", None)):
            try:
                yield action, B.build_tcl(action, uid, dev, pr)
            except B.BoardRefused:
                assert pr is None and action in ("design_id", "link_status", "all")


def test_no_generated_script_can_program_or_write():
    n = 0
    for action, tcl in all_scripts():
        n += 1
        low = tcl.lower()
        for w in FORBIDDEN_WORDS:
            assert w not in low, f"{action}: {w}"
        for cmd in set(re.findall(r"\b[a-z_]*hw[a-z_]*\b", tcl)):
            assert cmd in B.ALLOWED_HW or cmd.startswith("fda_") or cmd == "general", f"{action}: {cmd}"
        assert [ln.strip() for ln in tcl.splitlines() if "set_param" in ln] == ["set_param general.maxThreads 1"]
        for word in re.findall(r"fda_read ([0-9a-f]{16})", tcl):                    # every register scan word: read bit set, write bit clear, whitelisted read-only register, data 0
            v = int(word, 16)
            assert (v >> 45) & 1 == 1 and (v >> 44) & 1 == 0 and v & 0xFFFFFFFF == 0 and v >> 46 == 0 and ((v >> 32) & 0xFFF) in (0x000, 0x004, 0x008, 0x014)
    assert n == 7                                                                # five actions for the KR260, targets and SYSMON for the board without a profile


def test_check_tcl_refuses_planted_write_paths():
    ok = B.build_tcl("jtag_targets", "Xilinx/XFL1STT4HIMKA", "xck26_0", B.PROFILES["kr260"])
    bad = ["program_hw_devices [current_hw_device]", "set_property PROGRAM.FILE x.bit [current_hw_device]", "set_property PARAM.FREQUENCY 1000000 [current_hw_target]", "source designs/b58a_trigger/host/jtag_regs.tcl",
           "b58a_wr 0x00C 0x8", "write_hw_sysmon_reg x", "create_hw_cfgmem -hw_device x y", "exec rm -rf /", "set_param general.maxThreads 4", "run_hw_ila x", "open_hw_cfgmem x",
           "puts [fda_read 0000300000000000]", "puts [fda_read 0000201400000001]", "puts [fda_read 0000200c00000000]", "puts [fda_read 0000200000000001]", "scan_dr_hw_jtag_write x"]
    for line in bad:
        with pytest.raises(B.BoardRefused):
            B.check_tcl(ok + "\n" + line + "\n")
    B.check_tcl(ok)


def test_the_gt_ctrl_laser_register_and_other_writable_registers_are_not_readable_here():
    assert set(B.READ_REGS) == {"ID", "BUILD", "FEATURES", "GT_STAT"}
    from designs.b96_kr260_10g import regmap
    acc = {name: access for _, name, access, _, _ in regmap.REGS}
    assert all(acc[n] == "RO" and regmap.REGS[[r[1] for r in regmap.REGS].index(n)][0] == a for n, a in B.READ_REGS.items())
    feat = next(r for r in regmap.REGS if r[1] == "FEATURES")[4]
    for name in B.FEATURE_BITS.values():
        assert name == "ALWAYS_1" or name in feat
    gt = next(r for r in regmap.REGS if r[1] == "GT_STAT")[4]
    assert "TX_DONE" in gt and "BLOCK_LOCK" in gt


def test_constants_match_the_sources_they_cite():
    from flow import program
    assert B.ARTIX7_ROC == program.ROC
    from designs.b96_kr260_10g.host import b96_bench as bb, b96c_ppm
    assert B.GT_STAT_BITS == bb.GT_STAT_BITS
    assert {"TEMPERATURE": b96c_ppm.ROC["temp_c"], "VCCINT": b96c_ppm.ROC["vccint_v"], "VCCAUX": b96c_ppm.ROC["vccaux_v"], "VCCBRAM": b96c_ppm.ROC["vccbram_v"]} == B.KR260_ROC


FORBIDDEN_MODULES = ("flow.program", "hil", "debug_core", "b96_bench", "b96c_ppm", "b96f1_bypass", "jtag_regs", "hw_discover", "flow.eyescan.scan", "flow.eyescan.hw")
FORBIDDEN_NAMES = {"program_hw_devices", "b58a_wr", "b96_wr", "save_board", "run_vivado_tcl", "laser", "wr", "program"}


def test_no_navigator_code_imports_a_programming_or_register_write_path():
    """Walk every navigator module's syntax tree: no import of the programming flow, the bench drivers or the debug core; the only flow.hw names used are the guarded starters;
    no call or attribute named like a write."""
    for p in sorted((ROOT / "navigator").glob("*.py")):
        tree = ast.parse(p.read_text())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [(node.module or "") + "." + a.name for a in node.names] + [node.module or ""]
            for m in mods:
                assert not any(f in m for f in FORBIDDEN_MODULES), f"{p.name} imports {m}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in FORBIDDEN_NAMES, f"{p.name} uses .{node.attr}"
            if isinstance(node, ast.Name):
                assert node.id not in FORBIDDEN_NAMES, f"{p.name} uses {node.id}"
        if p.name == "boardops.py":
            used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "hw"}
            assert used <= {"preflight", "HwServer", "vivado_cmd", "HwError"}, used


def test_the_server_exposes_no_post_route_that_could_write():
    src = (ROOT / "navigator" / "server.py").read_text()
    routes = set(re.findall(r'path == "(/api/[a-z/_]+)"', src[src.index("def post"):src.index("def action")]))
    assert routes == {"/api/run/start", "/api/run/stop", "/api/board/run"}
    assert "innerHTML" not in (ROOT / "navigator" / "static" / "app.js").read_text()                # server text reaches the DOM only as text nodes


# --- over HTTP ---------------------------------------------------------------------------------------------------------------------------

class Live:
    def __init__(self, app):
        self.app = app
        self.srv = SV.make_server(app, port=0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]

    def req(self, method, path, headers=None, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        c.request(method, path, body=body, headers={"Host": f"127.0.0.1:{self.port}", **(headers or {})})
        r = c.getresponse()
        out = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return out

    def get(self, path):
        return self.req("GET", path, {"X-Navigator-Token": TOKEN})

    def post(self, path, obj, **h):
        hd = {"X-Navigator-Token": TOKEN, "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{self.port}", **h}
        st, _, b = self.req("POST", path, hd, json.dumps(obj))
        return st, json.loads(b) if b[:1] in (b"{", b"[") else b

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def web(env):
    runner = FakeRunner(env["handoff"])
    hl = H.Health(ROOT, env["handoff"], runner, config_dir=env["cfg"], sysfs_usb=env["tmp"] / "usb")
    hl._cache["models_view"] = (time.monotonic() + 1e6, MODELS)
    sp, tr = FakeSpawner(), FakeTransport(env["handoff"], KR + SYS_OK + REGS)
    app = SV.App(ROOT, env["handoff"], env["runs"], gate=lambda e: "owner", health=hl, token=TOKEN, state_dir=env["state"], spawner=sp, transport=tr)
    s = Live(app)
    s.sp, s.tr, s.env = sp, tr, env
    yield s
    s.close()


def test_http_start_live_and_board_round_trip(web):
    make_run(web.env["runs"])
    st, j = web.post("/api/run/start", dict(TASK))
    assert st == 200 and j["started"] is True and j["record"]["slot"]["job"].startswith("103S2:")
    web.sp.procs[0].finish()
    live = json.loads(web.get("/api/live")[2])
    assert live["runs"][0]["stage"] == "rtl-design-creation" and live["started"][0]["id"] == j["id"]
    det = json.loads(web.get("/api/live/run?id=20261120-100000-abcd")[2])
    assert det["gates"][0]["verdict"] == "FAIL" and web.get("/api/live/run?id=../../etc")[0] == 404
    opts = json.loads(web.get("/api/start/options")[2])
    assert "c10_dds_sine" in opts["tasks"] and opts["usage_stop_pct"] == 90 and "claude-sonnet-5-5" in opts["models"]["claude_code"]
    st, b = web.post("/api/board/run", {"board": "kr260", "action": "all", "confirm": "read"})
    assert st == 200 and b["ok"] is True and b["link"]["link_up"] is True
    lst = json.loads(web.get("/api/board")[2])
    assert lst["boards"][0]["last"]["action"] == "all" and lst["lock"]["held"] is False
    assert web.post("/api/board/run", {"board": "kr260", "action": "all"})[1]["refused"]                     # no confirmation: nothing runs
    assert len(web.tr.scripts) == 1


def test_http_post_rules_for_the_new_routes(web):
    ok = {"X-Navigator-Token": TOKEN, "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{web.port}"}
    for path in ("/api/run/start", "/api/run/stop", "/api/board/run"):
        body = json.dumps({"board": "kr260", "action": "all", "confirm": "read", **TASK})
        assert web.req("POST", path, {k: v for k, v in ok.items() if k != "X-Navigator-Token"}, body)[0] == 401                                       # no token
        assert web.req("POST", path, {"Cookie": f"{SV.COOKIE}={TOKEN}", "Content-Type": "application/json", "Origin": ok["Origin"]}, body)[0] == 403   # cookie alone
        assert web.req("POST", path, {**ok, "Origin": "http://evil.example"}, body)[0] == 403
        assert web.req("POST", path, {**ok, "Content-Type": "text/plain"}, body)[0] == 403
        assert web.req("GET", path, {"X-Navigator-Token": TOKEN})[0] == 404
    assert web.req("POST", "/api/run/start", ok, "not json")[0] == 400
    assert web.req("POST", "/api/run/start", ok, "[1]")[0] == 400
    assert web.req("POST", "/api/board/program", ok, "{}")[0] == 404
    assert web.sp.calls == [] and web.tr.scripts == [] and locks_in(web.env) == []


def test_http_stop_of_an_unknown_run_and_no_secrets_in_responses(web):
    make_run(web.env["runs"], secret=True)
    assert web.post("/api/run/stop", {"id": "n-20261120-100000-0000"})[1]["stopped"] is False
    for p in ("/api/live", "/api/live/run?id=20261120-100000-abcd", "/api/start/options", "/api/board"):
        st, _, b = web.get(p)
        assert st == 200 and SECRET.encode() not in b, p
    line = json.loads(web.get("/api/live/run?id=20261120-100000-abcd")[2])["audit_tail"][-1]["line"]
    assert "[redacted]" in line and SECRET not in line            # the page puts it in a text node, so the markup in it is inert


def test_guards_unit(env):
    lk = env["handoff"] / "x.lock"
    a = G.OwnedLock(lk, "103S2: job, 2026-11-20 10:00, expected end 11:00")
    a.take()
    with pytest.raises(G.LockBusy):
        G.OwnedLock(lk, "103S2: other, 2026-11-20 10:00, expected end 11:00").take()
    assert G.release_if_ours(lk, "103S2: other, 2026-11-20 10:00, expected end 11:00") is False and lk.is_file()
    assert a.release() is True and not lk.exists() and a.release() is False
    with pytest.raises(ValueError):
        G.OwnedLock(lk, "96F: not ours")
    assert ";" not in G.lock_text("a;b`c$(x)", 1) and "`" not in G.lock_text("a;b`c$(x)", 1) and "$" not in G.lock_text("a;b`c$(x)", 1)


# --- stage-1 follow-ups ------------------------------------------------------------------------------------------------------------------

def test_latency_page_says_which_build_the_stage_table_is():
    from navigator import sources as S
    v = S.latency_view(ROOT, "b96_kr260_10g")
    by = {c["file"]: c for c in v["chains"]}
    assert by["results/b96c/core_sim.json"]["clocks"] == 13 and by["results/b96c/core_sim.json"]["is_stage_table"] is True and "RATE_MATCH = 1" in by["results/b96c/core_sim.json"]["label"]
    assert by["results/b96c/core_sim_default.json"]["clocks"] == 11 and by["results/b96c/core_sim_default.json"]["is_stage_table"] is False and "RATE_MATCH = 0" in by["results/b96c/core_sim_default.json"]["label"]
    assert v["total_clocks"] == 13 and v["reconciled"] is True


def test_a_fresh_synthetic_scan_records_expected_points_and_the_page_reads_it(tmp_path):
    from flow.eyescan import capture as C, fake, hw as EH, scan
    cfg = scan.ScanConfig(target_ber=1e-3, hstep=16, vstep=40, vmax=120, label="fresh")
    cap = scan.run_scan(EH.EyeHW(fake.FakeBoard(seed=3)), cfg, conditions=lambda: {"temp_c": 50.0, "inside_roc": True}, link_ok=lambda: True, design=fake.design_info(), synthetic=True)
    assert cap["settings"]["expected_points"] == len(cap["points"]) > 0
    root = tmp_path / "repo"
    (root / "results" / "x").mkdir(parents=True)
    C.save(cap, root / "results" / "x" / "fresh.json") if hasattr(C, "save") else (root / "results" / "x" / "fresh.json").write_text(json.dumps(cap))
    from navigator import measure
    row = measure.listing(root)[0]
    assert row["complete"] is True and row["synthetic"] is True


def test_the_measured_96d3_captures_and_the_failed_run_display_honestly():
    from navigator import measure
    rows = {c["id"]: c for c in measure.listing(ROOT)}
    good = rows["results/b96d/hw/20261120_105134/lpm_1.json"]
    assert good["no_data"] is False and good["clk_phase_sel"] == 1 and good["width_ui"] == 0.71875 and good["width_ui_lo"] < good["width_ui"] < good["width_ui_hi"] and good["tx"]["diff"] == 24
    tx = rows["results/b96d/hw/20261120_105134/tx_d8.json"]
    assert tx["width_ui"] is None and tx["counts"]["shallow"] > 0 and tx["tx"]["diff"] == 8                    # not "no open row": points too shallow to vouch for the target depth
    bad = rows["results/b96d/hw/20261119_231836/lpm_1.json"]
    assert bad["no_data"] is True and bad["clk_phase_sel"] is None
    js = (ROOT / "navigator" / "static" / "app.js").read_text()
    assert "too shallow to vouch" in js and "NO DATA (no samples were counted)" in js and "Eye data on the board is not measured yet" not in js


def test_the_96f1_bypass_build_is_listed_with_its_numbers():
    from navigator import sources as S
    b = {x["id"]: x for x in S.builds(ROOT)}
    bp, ctl = b["b96f1/rm_gp_bypass"], b["b96f1/rm_gp"]
    assert bp["wns_ns"] == 0.09 and bp["whs_ns"] == 0.01 and bp["gates_failing"] == [] and bp["timing_met"] is True and bp["vivado_version"] == "2026.1"
    assert bp["resources"]["lut"] == ctl["resources"]["lut"] + 36 and bp["design"].endswith("rm_gp_bypass") and bp["build_id"] != ctl["build_id"]


# --- review fixes (Sonnet safety review of stage 2) -----------------------------------------------------------------------------------------

def test_identical_lock_texts_never_release_each_others_lock(env):
    lk = env["handoff"] / "board.lock"
    a = G.OwnedLock(lk, "103S2: same text")
    b = G.OwnedLock(lk, "103S2: same text")                   # a refused take with identical text (double click in one minute)
    a.take()
    with pytest.raises(G.LockBusy):
        b.take()
    assert b.release() is False and lk.is_file()              # a take that was refused owns nothing
    assert G.lock_text("job", 1) != G.lock_text("job", 1)     # and real lock texts carry a nonce, so two takes never match
    assert a.release() is True


def test_two_simultaneous_board_actions_do_not_touch_each_others_locks(env):
    gate, seen = threading.Event(), []

    class Slow(FakeTransport):
        def run_tcl(self, tcl, name):
            gate.wait(5)
            return super().run_tcl(tcl, name)
    tr = Slow(env["handoff"], KR)
    ops = B.BoardOps(env["handoff"], FakeRunner(env["handoff"]), env["cfg"], tr)
    t = threading.Thread(target=lambda: seen.append(ops.run("kr260", "jtag_targets")))
    t.start()
    for _ in range(100):
        if (env["handoff"] / "board.lock").is_file():
            break
        time.sleep(0.02)
    r2 = ops.run("kr260", "jtag_targets")
    assert r2["ok"] is False and "already running" in r2["refused"] and (env["handoff"] / "board.lock").is_file()
    gate.set()
    t.join()
    assert seen[0]["ok"] is True and locks_in(env) == []


def test_slot_script_exit_zero_with_odd_output_does_not_leak_a_slot(env):
    class Odd(FakeRunner):
        def run(self, argv, timeout=20, cwd=None, env=None):
            if argv[0] == "bash" and argv[1].endswith("take_heavy_slot.sh"):
                rc, out, err = super().run(argv, timeout, cwd, env)
                return 0, "warning: something\n", ""              # took the lock but printed no path
            return super().run(argv, timeout, cwd, env)
    slot = G.HeavySlot(env["handoff"], Odd(env["handoff"]), G.lock_text("x", 1))
    with pytest.raises(G.LockBusy):
        slot.take()
    assert locks_in(env) == []


@pytest.mark.parametrize("line", ["fda_scan 0000100000000001", "scan_dr_hw_jtag 64 -tdi 0000100000000001", "puts [fda_read 00002014000000000]", "puts [fda_read $x]",
                                  "puts [fda_read 0000200000000000 ]; fda_scan 0000100000000000", "set c fda_scan; $c 0000100000000001", "puts [fda_read 0000201400000000"[:0] + "puts [fda_read 0000201400000000;x]",
                                  "append x y", "puts [fda_read 0000201400000000]\n[fda_scan 0000100000000001]"])
def test_check_tcl_is_structural_not_just_a_pattern(line):
    ok = B.build_tcl("all", "Xilinx/XFL1STT4HIMKA", "xck26_0", B.PROFILES["kr260"])
    with pytest.raises(B.BoardRefused):
        B.check_tcl(ok + "\n" + line + "\n")


def test_ok_needs_the_actions_own_evidence_and_serials_are_masked_in_errors(env):
    ops, _ = make_ops(env, "ERROR: Vivado crashed\n")
    r = ops.run("kr260", "all")
    assert r["ok"] is False
    ops, _ = make_ops(env, "FDA-ERR sysmon no device on localhost:3121/xilinx_tcf/Xilinx/XFL1STT4HIMKA\nFDA-TARGET-ERROR Xilinx/XFL1STT4HIMKA busy Xilinx/XFL1STT4HIMKA\n")
    r = ops.run("kr260", "sysmon")
    assert "XFL1STT4HIMKA" not in json.dumps(r) and "Xilinx/...IMKA" in json.dumps(r)
    ops, _ = make_ops(env, "FDA-REG ID 96a00001\nFDA-REG BUILD 1\n")
    assert ops.run("kr260", "design_id")["ok"] is False                        # FEATURES missing


def test_post_spawn_failure_stops_the_group_and_frees_the_slot(env):
    rc, _, sp = make_rc(env)
    killed = []
    rc.killpg = lambda pg, sig: killed.append((pg, sig))
    rc._save = lambda: (_ for _ in ()).throw(OSError("disk full"))
    r = rc.start(dict(TASK))
    assert r["started"] is False and "could not be registered" in r["refused"] and killed and locks_in(env) == [] and rc.recs == {}


def test_a_failed_registry_save_does_not_stop_a_start(env):
    rc, _, sp = make_rc(env)
    rc.state_dir = Path("/proc/nope/state")
    rc.state_file = rc.state_dir / "x.json"
    assert rc.start(dict(TASK))["started"] is True and rc.save_error
    sp.procs[0].finish()


def test_children_that_outlive_the_leader_are_stopped_before_the_slot_is_freed(env, monkeypatch):
    monkeypatch.setattr(R, "STOP_GRACE_S", 1)

    class Orphan(R.RunControl):
        def build(self, p):
            code = "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])"
            return [sys.executable, "-c", code], {"kind": "task", "target": "c10_dds_sine"}
    rc = Orphan(ROOT, env["handoff"], env["runs"], FakeRunner(env["handoff"]), env["state"], lambda: MODELS)
    r = rc.start({"confirm": "start"})
    assert r["started"]
    pg = rc.recs[r["id"]]["pgid"]
    try:
        for _ in range(100):
            if rc.records()[0]["status"] == "ended":
                break
            time.sleep(0.1)
        assert rc.records()[0]["status"] == "ended" and locks_in(env) == []
        assert not rc.group_alive(pg), "a child outlived the run and its slot"
    finally:
        try:
            os.killpg(pg, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_a_forged_registry_entry_is_not_signalled(env):
    rc, _, _ = make_rc(env)
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        sid = "n-20261120-000000-aaaa"
        rc.recs[sid] = {"id": sid, "status": "running", "pid": bystander.pid, "pgid": bystander.pid, "starttime": R.proc_start_time(bystander.pid), "argv_full": ["python", "-m", "agent"], "slot_text": ""}
        sent = []
        rc.killpg = lambda pg, sig: sent.append(pg)
        assert rc.stop(sid)["stopped"] is False and sent == [] and bystander.poll() is None
    finally:
        bystander.kill()
        bystander.wait()


def test_a_resolved_table_that_sends_a_purpose_to_opus_over_the_network_blocks_the_start(env):
    rc, _, sp = make_rc(env)
    rc.models_view = lambda: MODELS_BAD
    r = rc.start(dict(TASK))
    assert r["started"] is False and "forbidden model" in r["refused"] and sp.calls == [] and locks_in(env) == []


def test_navigator_runs_never_reach_the_hardware_stage(env):
    """Planner, 2026-11-20: stage 9 (configuration-and-debug) has the board tools (program, bringup, capture), which need
    _handoff/board.lock; a navigator-started run holds only a heavy slot, so both run kinds stop after stage 8."""
    from navigator import runctl
    assert runctl.NAV_STOP_AFTER == 8
    for req in (TASK, PROJ):
        rc, _, sp = make_rc(env)
        r = rc.start(dict(req))
        assert r["started"], r
        argv = sp.calls[0]["argv"]
        assert argv[argv.index("--stop-after") + 1] == "8", argv
        sp.procs[0].finish(0)
        for _ in range(100):
            if rc.records()[0]["status"] == "ended":
                break
            time.sleep(0.05)
