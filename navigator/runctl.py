"""Start an agent run from the navigator with the CLI's guards, watch it, and stop it (its own process group only).

The command it starts is always one of the agent's own CLI forms, built here from validated fields, never from a string the browser sends:

    python -m agent run <task spec.md> --board B --harness H --cc-model M | --model M --cc-effort E --harness-arm A --max-usd N
    python -m agent resume designs/<managed project> "<request>" --scope c1,c2 --harness H ... --max-usd N

Guards, in this order, each of which refuses with its reason and starts nothing: the access gate (the server calls it on every request and again here), the
field checks (names looked up in lists the service builds, a budget cap, no Fable, no Opus, no OpenRouter model of Anthropic), at most one navigator run at a
time, the usage check (``_handoff/usage_check.sh``; a reading at or above the owner's stop refuses), and a heavy slot through ``_handoff/take_heavy_slot.sh``.
The slot is released when the process ends, on every path, only if the lock file still holds the exact text written.

A run is its own session and process group (``start_new_session``), so ``stop`` signals that group alone: SIGTERM, then SIGKILL after a grace period. It
only ever signals a process this module started and recorded (pid, start time and group are checked again before a signal). It never signals by process name.
The registry is a small JSON file so a restarted navigator still knows its runs and releases the slot of one that has gone.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from navigator import guards, redact
from navigator import progress as P
from navigator import sources as S

MAX_USD = 10.0
DEFAULT_USD = 3.0
MAX_ACTIVE = 1                                  # navigator-started runs at once (the PC allows two heavy jobs in all, shared with other sessions)
RUN_HOURS = 6                                   # the agent's own wall limit per run (RUN_LIMITS seconds)
STOP_GRACE_S = 20
EFFORTS = ("low", "medium", "high")
ARMS = ("H1", "H2", "H9")
CC_DEFAULTS = ("claude-haiku-5-5", "claude-sonnet-5-5")
FORBIDDEN_MODEL = re.compile(r"fable|opus|anthropic[/:.]", re.I)
MODEL_OK = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:+-]{0,80}")
SEGMENT = re.compile(r"[A-Za-z0-9_.-]{1,80}")
START_ID = re.compile(r"n-\d{8}-\d{6}-[0-9a-f]{4}")



#: Planner, 2026-11-20 (103S2 review): a navigator-started run never reaches stage 9 (configuration-and-debug), the only stage
#: with board tools (program, bringup, debug capture). Those take the board, which is owner-run under _handoff/board.lock; the
#: navigator only holds a heavy slot for a run. agent/graph/run.py stops after the stage given by --stop-after passes.
NAV_STOP_AFTER = 8

class Refused(Exception):
    """A guard refused; the message is the reason shown to the owner. Nothing was started."""


class Proc:
    """What a spawner returns: the pid and a way to wait."""

    def __init__(self, popen: subprocess.Popen[bytes]):
        self.p, self.pid = popen, popen.pid

    def wait(self, timeout: float | None = None) -> int | None:
        try:
            return self.p.wait(timeout)
        except subprocess.TimeoutExpired:
            return None

    def poll(self) -> int | None:
        return self.p.poll()


class Spawner:
    """The only place a run is started: a fixed argv (no shell), its own session, output to a log file under the run directory."""

    def spawn(self, argv: list[str], cwd: Path, env: dict[str, str], log: Path) -> Proc:
        log.parent.mkdir(parents=True, exist_ok=True)
        fh = open(log, "ab")
        try:
            p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            fh.close()
        return Proc(p)


def proc_start_time(pid: int) -> int | None:
    """Field 22 of /proc/<pid>/stat (clock ticks since boot): with the pid it identifies one process, so a reused pid is never signalled."""
    try:
        txt = Path(f"/proc/{pid}/stat").read_text()
        return int(txt.rsplit(")", 1)[1].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def pgid_of(pid: int) -> int | None:
    try:
        return os.getpgid(pid)
    except OSError:
        return None


def now_s() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class RunControl:
    def __init__(self, root: Path, handoff: Path, runs_dir: Path, runner: Any, state_dir: Path, models_view: Callable[[], dict[str, Any]],
                 spawner: Spawner | None = None, killpg: Callable[[int, int], None] = os.killpg, python: str | None = None,
                 gate: Callable[[str], Any] | None = None, usage_stop: int | None = None):
        self.root, self.handoff, self.runs_dir = Path(root), Path(handoff), Path(runs_dir)
        self.runner, self.state_dir, self.models_view = runner, Path(state_dir), models_view
        self.spawner, self.killpg = spawner or Spawner(), killpg
        self.python = python or sys.executable
        self.gate, self.usage_stop = gate, usage_stop
        self.lock = threading.RLock()
        self.start_lock = threading.Lock()
        self.save_error: str | None = None
        self.recs: dict[str, dict[str, Any]] = {}
        self.slots: dict[str, guards.HeavySlot] = {}
        self.procs: dict[str, Proc] = {}
        self.threads: list[threading.Thread] = []
        self.state_file = self.state_dir / "navigator_runs.json"
        self._load()

    # -- the registry ---------------------------------------------------------------------------------------------------------------
    def _load(self) -> None:
        try:
            d = json.loads(self.state_file.read_text())
            self.recs = {k: v for k, v in d.items() if START_ID.fullmatch(k) and isinstance(v, dict) and isinstance(v.get("pid"), int) and v["pid"] > 1 and isinstance(v.get("pgid"), int) and v["pgid"] > 1}
        except (OSError, ValueError, AttributeError):
            self.recs = {}

    def _save(self) -> None:
        """A registry that cannot be written must not stop a start or a release: the in-memory record is still right for this navigator's life (only restart recovery is lost)."""
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.recs, indent=1))
            tmp.replace(self.state_file)
            self.save_error = None
        except OSError as e:
            self.save_error = redact.brief(str(e), 120)

    def reconcile(self) -> None:
        """At start-up: a record still 'running' whose process is gone is ended and its slot released; one still alive gets a watcher again."""
        with self.lock:
            for sid, r in self.recs.items():
                if r.get("status") != "running":
                    continue
                if self._alive(r):
                    t = threading.Thread(target=self._watch_pid, args=(sid,), daemon=True)
                    t.start()
                    self.threads.append(t)
                else:
                    self._end(sid, None, "the process was gone when the navigator started")
            self._save()

    @staticmethod
    def _alive(r: dict[str, Any]) -> bool:
        pid = r.get("pid")
        return isinstance(pid, int) and proc_start_time(pid) == r.get("starttime") and r.get("starttime") is not None

    def _end(self, sid: str, code: int | None, why: str) -> None:
        r = self.recs[sid]
        if r.get("status") != "running":
            return
        r.update(status="ended", exit_code=code, ended=now_s(), ended_why=why)
        slot = self.slots.pop(sid, None)
        if slot is not None:
            released = slot.release()
        else:                                                                 # a restored record: release by the recorded file and text
            released = bool(r.get("slot_file")) and guards.release_if_ours(Path(r["slot_file"]), r.get("slot_text", ""))
        r["slot_released"] = released
        self._discover(sid)

    @staticmethod
    def group_alive(pg: int) -> bool:
        try:
            os.killpg(pg, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def _reap_group(self, pg: int) -> None:
        """The leader has gone: its children (Vivado, claude) must be gone too before the heavy slot is released; any that ignore SIGTERM get SIGKILL after the grace period.
        Only a group this module created is probed, and only while it still has members."""
        end = time.time() + STOP_GRACE_S
        if self.group_alive(pg):
            try:
                self.killpg(pg, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                return
        while time.time() < end and self.group_alive(pg):
            time.sleep(0.3)
        if self.group_alive(pg):
            try:
                self.killpg(pg, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def _watch(self, sid: str) -> None:
        try:
            proc = self.procs.get(sid)
            code = proc.wait() if proc else None
            self._reap_group(self.recs[sid]["pgid"])
        except BaseException:
            code = None
        finally:                                                # the slot is released and the record saved whatever happened above
            with self.lock:
                try:
                    self._end(sid, code, "the process ended")
                finally:
                    self._save()

    def _watch_pid(self, sid: str) -> None:
        while True:
            with self.lock:
                if self.recs[sid].get("status") != "running":
                    return
                if not self._alive(self.recs[sid]):
                    pg = self.recs[sid]["pgid"]
                    self.lock.release()
                    try:
                        self._reap_group(pg)
                    finally:
                        self.lock.acquire()
                    self._end(sid, None, "the process ended")
                    self._save()
                    return
            time.sleep(3)

    # -- what the form offers -------------------------------------------------------------------------------------------------------
    def tasks(self) -> dict[str, Path]:
        """Task specs a run may be started on: benchmark/course/tasks/*/spec.md (a course task; never the held-out sets)."""
        base = self.root / "benchmark" / "course" / "tasks"
        return {p.parent.name: p for p in sorted(base.glob("*/spec.md")) if SEGMENT.fullmatch(p.parent.name) and not p.is_symlink()} if base.is_dir() else {}

    def boards(self) -> list[str]:
        try:
            from flow import board_catalogue as cat
            return sorted(k for k, v in cat.load().items() if v.get("targetable") and SEGMENT.fullmatch(k))
        except Exception:
            return []

    def allowed_models(self) -> dict[str, list[str]]:
        mv = self.models_view() or {}
        rows = mv.get("table") or []
        cc = {r["model"] for r in rows if r.get("kind") == "claude_code" and r.get("model")} | set(CC_DEFAULTS)
        net = {r["model"] for r in rows if r.get("kind") in ("openrouter", "openai_compatible") and r.get("model")}
        ok = lambda ms: sorted(m for m in ms if MODEL_OK.fullmatch(m) and not FORBIDDEN_MODEL.search(m))          # noqa: E731
        return {"claude_code": ok(cc), "deepagents": ok(net)}

    def options(self) -> dict[str, Any]:
        mv = self.models_view() or {}
        proj = [p for p in S.project_list(self.root) if "error" not in p]
        comps = {}
        for p in proj:
            pr = S.load_project(self.root, p["name"])
            if pr is not None:
                comps[p["name"]] = [{"name": c.name, "ownership": c.ownership} for c in pr.components if c.ownership == "owned"]
        return {"tasks": sorted(self.tasks()), "projects": proj, "owned_components": comps, "boards": self.boards(), "arms": list(ARMS), "arm_note": "H1 is the CLI default; A0 (no arm) is chosen by ticking none; an arm applies to a task run (the resume command has no arm option)",
                "efforts": list(EFFORTS), "models": self.allowed_models(), "model_table": mv, "max_usd": MAX_USD, "default_usd": DEFAULT_USD,
                "usage_stop_pct": guards.USAGE_STOP_PCT, "active_limit": MAX_ACTIVE, "never": "Fable, Opus, or an Anthropic model through OpenRouter; the owner's --allow-fable flag is never passed",
                "guards": ["access gate", "usage check at or above the stop refuses", "one navigator run at a time", "a heavy slot through take_heavy_slot.sh, released when the run ends"]}

    # -- validation -----------------------------------------------------------------------------------------------------------------
    def build(self, p: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        """The argv and a safe summary, or Refused. Pure: starts nothing."""
        if not isinstance(p, dict):
            raise Refused("the request body must be a JSON object")
        kind = p.get("kind")
        if kind == "answer":
            return self.build_answer(p)
        if kind == "example":
            return self.build_example(p)
        harness = p.get("harness", "claude_code")
        if harness not in ("claude_code", "deepagents"):
            raise Refused("harness must be claude_code or deepagents")
        model = p.get("model")
        allowed = self.allowed_models()[harness]
        if not isinstance(model, str) or not MODEL_OK.fullmatch(model):
            raise Refused("pick a model from the resolved table")
        if FORBIDDEN_MODEL.search(model):
            raise Refused("Fable, Opus and Anthropic models through OpenRouter are never started from the navigator")
        if model not in allowed:
            raise Refused(f"model {model!r} is not one the resolved table offers for {harness}")
        effort = p.get("effort", "medium")
        if effort not in EFFORTS:
            raise Refused(f"effort must be one of {', '.join(EFFORTS)}")
        usd = p.get("max_usd", DEFAULT_USD)
        if isinstance(usd, bool) or not isinstance(usd, (int, float)) or not (0 < float(usd) <= MAX_USD):
            raise Refused(f"the budget must be above 0 and at most ${MAX_USD:g}")
        usd = float(usd)
        argv = [self.python, "-m", "agent"]
        summary_hw = "no hardware: navigator runs stop after stage 8; stage 9 (configuration-and-debug: program, bringup, capture) needs board.lock and is run from the CLI by the owner"
        summary: dict[str, Any] = {"hardware": summary_hw, "kind": kind, "harness": harness, "model": model, "effort": effort, "max_usd": usd}
        mflag = ["--cc-model", model, "--cc-effort", effort] if harness == "claude_code" else ["--model", model]
        if kind == "task":
            t = p.get("task")
            specs = self.tasks()
            if not isinstance(t, str) or t not in specs:
                raise Refused("pick a task from the list")
            board = p.get("board", "nexys_a7_100t")
            if not isinstance(board, str) or board not in self.boards():
                raise Refused("pick a board the agent can target")
            arms = p.get("arms", ["H1"])
            if not isinstance(arms, list) or not all(a in ARMS for a in arms) or len(set(arms)) != len(arms):
                raise Refused(f"arms must be a list of {', '.join(ARMS)} (empty for the A0 baseline)")
            arg_arms = ",".join(arms) if arms else "A0"
            rel = specs[t].relative_to(self.root).as_posix()
            argv += ["run", rel, "--board", board, "--harness", harness, *mflag, "--harness-arm", arg_arms, "--max-usd", f"{usd:g}", "--stop-after", str(NAV_STOP_AFTER)]
            summary.update(target=t, board=board, arm=arg_arms, spec=rel)
        elif kind == "project":
            name = p.get("project")
            if not isinstance(name, str) or not SEGMENT.fullmatch(name) or name not in {x["name"] for x in S.project_list(self.root) if "error" not in x}:
                raise Refused("pick a managed project from the list")
            comps = p.get("components", [])
            if not isinstance(comps, list) or not all(isinstance(c, str) and SEGMENT.fullmatch(c) for c in comps):
                raise Refused("components must be a list of component names")
            req = p.get("request", "")
            if not isinstance(req, str):
                raise Refused("the change request must be text")
            req = re.sub(r"[\x00-\x1f\x7f]", " ", req).strip()
            if len(req) > 400 or req.startswith("-"):
                raise Refused("the change request is at most 400 characters and cannot start with '-'")
            if not req:
                raise Refused("write the change request: the agent resumes the design to make it")
            view = S.scope_view(self.root, name, comps, req)           # the agent's own resolution of the scope (managed.resolve_request)
            if view is None:
                raise Refused("no such managed project")
            if view.get("ask") or not view.get("will_touch"):
                raise Refused("the agent would ask first: " + str(view.get("ask") or "the request names no component"))
            argv += ["resume", f"designs/{name}", req]
            if comps:
                argv += ["--scope", ",".join(comps)]
            argv += ["--harness", harness, *mflag, "--max-usd", f"{usd:g}", "--stop-after", str(NAV_STOP_AFTER)]
            summary.update(target=name, components=list(view["will_touch"]), request=req[:120])
        else:
            raise Refused("kind must be task or project")
        if any(a == "--allow-fable" for a in argv):                                  # never reachable; a tripwire
            raise Refused("--allow-fable is never passed")
        return argv, summary

    def build_example(self, p: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        """Brief 195: re-run a reproducible example with its pinned setup. The browser sends the example's name and, optionally, a lower cost cap: model, effort, harness, arm
        and stop stage are the pins' (``agent/repro/examples.yaml``) and cannot be changed here, which is the point. The command is ``agent example run <name> --no-slot`` (the navigator
        holds the slot); the child runs the pre-flight again and refuses, naming the check, when a pin does not hold."""
        from agent.repro import registry as RR
        try:
            reg = RR.load()
        except Exception as e:                                           # noqa: BLE001
            raise Refused("the examples file cannot be read: " + redact.brief(str(e), 80))
        name = p.get("example")
        if not isinstance(name, str) or name not in {e["name"] for e in reg["examples"]}:
            raise Refused("pick an example from the list")
        cap = float(reg["pins"]["max_usd"])
        usd = p.get("max_usd", cap)
        if isinstance(usd, bool) or not isinstance(usd, (int, float)) or not (0 < float(usd) <= cap):
            raise Refused(f"the budget must be above 0 and at most the pinned ${cap:g}")
        argv = [self.python, "-m", "agent", "example", "run", name, "--no-slot", "--max-usd", f"{float(usd):g}"]
        return argv, {"kind": "example", "target": f"ex_{name}", "example": name, "max_usd": float(usd), "hardware": "no hardware: the pinned setup stops after timing closure (stage 6)",
                      "harness": reg["pins"]["harness"], "model": reg["pins"]["cc_model"], "effort": reg["pins"]["cc_effort"]}

    def build_answer(self, p: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        """Brief 182: resume a run that paused on a question of its own, with the user's answer: ``python -m agent resume <run id> --reply '{"answer": ...}'``.
        The run is looked up in the list of run directories the service built (never named by path); the answer is data in one argv element and cannot start a flag."""
        rid = p.get("run")
        if not isinstance(rid, str) or rid not in P.run_ids(self.runs_dir, 200):
            raise Refused("pick a run from the list")
        try:
            pend = json.loads((self.runs_dir / rid / "pending.json").read_text()).get("paused") or {}
        except (OSError, ValueError, AttributeError):
            pend = {}
        if pend.get("kind") != "question":
            raise Refused("that run is not waiting for an answer to a question of its own")
        ans = p.get("answer")
        if not isinstance(ans, str):
            raise Refused("the answer must be text")
        ans = re.sub(r"[\x00-\x1f\x7f]", " ", ans).strip()
        if not ans or len(ans) > 400:
            raise Refused("the answer is 1 to 400 characters")
        argv = [self.python, "-m", "agent", "resume", rid, "--reply", json.dumps({"answer": ans})]
        return argv, {"kind": "answer", "target": rid, "hardware": "no hardware: the run resumes at its question", "answer": ans[:80]}

    # -- start, stop, list ----------------------------------------------------------------------------------------------------------
    def active(self) -> list[str]:
        return [k for k, r in self.recs.items() if r.get("status") == "running" and (k in self.procs or self._alive(r))]

    def start(self, p: dict[str, Any]) -> dict[str, Any]:
        """Guards, then spawn. The registry lock is held only to read or change the registry, never while the usage check or the slot script runs (they can take a minute),
        so the Live page keeps answering; a second start meanwhile is refused."""
        if not self.start_lock.acquire(blocking=False):
            return {"started": False, "refused": "another start is in progress"}
        try:
            return self._start(p)
        finally:
            self.start_lock.release()

    def _start(self, p: dict[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(p, dict) or p.get("confirm") != "start":
                raise Refused("a start needs the confirmation the form sends")
            if self.gate is not None:
                try:
                    self.gate("python -m navigator (start a run)")
                except Exception as e:                          # AccessDenied
                    raise Refused("access gate: " + redact.text(str(e))[:160])
            argv, summary = self.build(p)
            for row in (self.models_view() or {}).get("table") or []:      # the CLI applies the whole resolved table, not just the flag: refuse if a network purpose names a forbidden model
                if row.get("kind") in ("openrouter", "openai_compatible", "anthropic_api") and FORBIDDEN_MODEL.search(str(row.get("model") or "")):
                    raise Refused(f"the resolved model table sends purpose {row.get('name')!r} to a forbidden model ({row.get('model')}) over the network: fix the model files first")
            with self.lock:
                busy = self.active()
            if len(busy) >= MAX_ACTIVE:
                raise Refused(f"a navigator run is already going ({', '.join(busy)}); one at a time")
            ok, why, reading = guards.usage_guard(self.handoff, self.runner, self.usage_stop)
            if not ok:
                raise Refused(why)
            sid = f"n-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
            text = guards.lock_text(f"agent run {summary.get('target', '')[:40]} (Vivado impl, peak 6G)", RUN_HOURS)
            slot = guards.HeavySlot(self.handoff, self.runner, text)
            try:
                slot.take()
            except guards.LockBusy as e:
                raise Refused(str(e))
            started = time.time()
            try:
                log = self.runs_dir / "_navigator" / f"{sid}.log"
                proc = self.spawner.spawn(argv, self.root, dict(os.environ), log)
            except BaseException:
                guards.release_all(slot)
                raise
        except Refused as e:
            return {"started": False, "refused": str(e)}
        try:
            with self.lock:
                self.slots[sid] = slot
                self.procs[sid] = proc
                rec = {"id": sid, "status": "running", "started": now_s(), "started_epoch": started, "pid": proc.pid, "pgid": pgid_of(proc.pid) or proc.pid,
                       "starttime": proc_start_time(proc.pid), "summary": summary, "argv_full": list(argv), "command": [Path(argv[0]).name if i == 0 else a for i, a in enumerate(argv)][:40],
                       "log": f"runs/_navigator/{sid}.log", "slot_file": str(slot.lock), "slot_text": text, "run_id": None, "usage": {"percent": reading["percent"] if reading else None}}
                self.recs[sid] = rec
                self._save()
                t = threading.Thread(target=self._watch, args=(sid,), daemon=True)
                t.start()
                self.threads.append(t)
                return {"started": True, "id": sid, "record": self._public(rec)}
        except BaseException as e:                         # bookkeeping failed after the process started: stop its group and free the slot rather than leave it unwatched
            try:
                self.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
            with self.lock:
                self.recs.pop(sid, None)
                self.slots.pop(sid, None)
                self.procs.pop(sid, None)
            guards.release_all(slot)
            if isinstance(e, Exception):
                return {"started": False, "refused": "the run could not be registered, so it was stopped and its slot released: " + redact.brief(str(e), 100)}
            raise

    def stop(self, sid: str) -> dict[str, Any]:
        with self.lock:
            r = self.recs.get(sid) if isinstance(sid, str) and START_ID.fullmatch(sid) else None
            if r is None:
                return {"stopped": False, "refused": "no such run started from this navigator: only a run it started can be stopped here"}
            if r.get("status") != "running":
                return {"stopped": False, "refused": "that run has already ended"}
            if not self._alive(r) and sid not in self.procs:
                return {"stopped": False, "refused": "the process is not the one that was started (gone, or its pid reused): nothing was signalled"}
            pid, pg = r["pid"], r["pgid"]
            if pid <= 1 or pid != pg or pgid_of(pid) != pg or proc_start_time(pid) != r["starttime"] or not self._cmdline_ok(r):
                return {"stopped": False, "refused": "the process is not the leader of its own group any more: nothing was signalled"}
            try:
                self.killpg(pg, signal.SIGTERM)
            except ProcessLookupError:
                return {"stopped": False, "refused": "the process had already gone"}
            r["stop_requested"] = now_s()
            self._save()
            t = threading.Thread(target=self._escalate, args=(sid, pid, pg, r["starttime"]), daemon=True)
            t.start()
            self.threads.append(t)
            return {"stopped": True, "id": sid, "note": f"SIGTERM sent to the run's process group; SIGKILL follows after {STOP_GRACE_S} s if it is still there"}

    @staticmethod
    def _cmdline_ok(r: dict[str, Any]) -> bool:
        """The process must still carry the argv this module started it with (a forged or stale registry entry naming another process fails here)."""
        try:
            got = Path(f"/proc/{r['pid']}/cmdline").read_bytes().split(b"\0")[:-1]
        except OSError:
            return False
        return [g.decode(errors="replace") for g in got] == list(r.get("argv_full") or ["\0"])

    def _escalate(self, sid: str, pid: int, pg: int, starttime: int | None) -> None:
        """After SIGTERM: SIGKILL the group if anything in it is still there when the grace period ends (the leader going is not enough)."""
        end = time.time() + STOP_GRACE_S
        while time.time() < end and self.group_alive(pg):
            time.sleep(0.5)
        if self.group_alive(pg):
            try:
                self.killpg(pg, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def _discover(self, sid: str) -> None:
        """Find the run directory of a started run: the run id its output printed, else the one new directory created since the start (the task's own name)."""
        try:
            self._discover_inner(sid)
        except Exception:                                  # a malformed record file in the run directory must not break the watcher
            pass

    def _discover_inner(self, sid: str) -> None:
        r = self.recs[sid]
        if r.get("run_id"):
            return
        found = None
        try:
            txt = (self.root / r["log"]).read_text(errors="replace")[:200_000] if (self.root / r["log"]).is_file() else ""
            if not txt:
                txt = (self.runs_dir / "_navigator" / f"{sid}.log").read_text(errors="replace")[:200_000]
        except OSError:
            txt = ""
        for m in re.finditer(r'"run_id":\s*"([A-Za-z0-9][A-Za-z0-9_.-]{0,80})"', txt):
            if (self.runs_dir / m.group(1) / "config.json").is_file():
                found = m.group(1)
        if found is None:
            claimed = {x.get("run_id") for x in self.recs.values()}
            want = (r.get("summary") or {}).get("target")
            for rid in sorted(P.run_ids(self.runs_dir, 60)):
                cfgp = self.runs_dir / rid / "config.json"
                try:
                    fresh = cfgp.stat().st_mtime >= r["started_epoch"] - 2
                    cfg = json.loads(cfgp.read_text())
                    name = cfg.get("name") if isinstance(cfg, dict) else None
                except (OSError, ValueError):
                    continue
                if fresh and rid not in claimed and name == want:
                    found = rid
                    break
        if found:
            r["run_id"] = found

    def _public(self, r: dict[str, Any]) -> dict[str, Any]:
        keys = ("id", "status", "started", "ended", "exit_code", "ended_why", "summary", "command", "log", "run_id", "stop_requested", "slot_released", "pid")
        out = {k: r.get(k) for k in keys if k in r}
        out["slot"] = {"job": r.get("slot_text"), "released": r.get("slot_released")}
        return out

    def records(self) -> list[dict[str, Any]]:
        with self.lock:
            for sid, r in self.recs.items():
                if r.get("status") == "running":
                    self._discover(sid)
            return [self._public(r) for _, r in sorted(self.recs.items(), reverse=True)]
