"""The stage map of a run (brief 238): where the agent is, as a list of recorded events and the state of every stage after each one.

Read-only, like ``progress.py``, and from the run directory only. The stages, their visit limits and the allowed route-backs come from ``agent.graph.stages.MACHINE``,
so a stage added there appears by itself. Every event below is a row some file of the run holds; nothing is interpolated and no step is invented.

Two sources, named in the answer (``source.mode``):

* ``trace``: the run has ``trace.jsonl`` ``stage_start`` rows (brief 182 onward). Events come from its ``kind: "event"`` rows (``stage_start``, ``stage_end``, ``build_step``,
  ``console``, ``console_end``, ``slot_wait``, ``permission_stop``, ``permission_granted``, ``request``) with their times, the gate results of ``<design>/build/audit.jsonl``
  (every ``gates`` call, with its time) and the roles of ``role_usage.jsonl`` (which carry no time: they are placed right after their stage entry, in file order).
* ``role_usage``: an older run, or a folder kept without its trace and audit log (the 213 run folders). The order of the ``role_usage.jsonl`` rows (stage, visit, role) is the
  order of the visits; failing gates come from ``routing_events.jsonl`` ``ledger_entry`` rows; whether a visit passed is read from where the run went next. These rows carry no times.

``pending.json`` (a run waiting for a question, a permission, a review or a pause) and ``summary.json`` (the run's end and its stop reason) are read in both.

Event kinds mapped (the ``kind`` of each event in ``frames``): ``enter`` (stage_start, or a role_usage visit seen for the first time), ``role`` (a role_usage row), ``gate`` (an audit
``gates`` call, or a ledger_entry), ``leave`` (stage_end, or inferred in the role_usage mode), ``step`` (build_step start/end, console/console_end), ``wait`` (slot_wait, permission_stop,
a pause request, pending.json), ``resume`` (permission_granted, a pause request done), ``request`` (any other request row) and ``end`` (summary.json).

Key names avoid the words ``redact.scrub`` drops (text, message, key ...): the page receives exactly what is built here.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from navigator import progress as PG
from navigator import redact

MAX_FRAMES = 600
SLOT_WAIT_RECENT_S = 300                                        # the same window summary.py uses for "waiting for a Vivado slot"
ROLE_NAMES = {"clarify": "Clarifier", "model": "Modeller", "tests": "Verifier", "rtl": "Designer"}     # as site/agent_arch.py ROLE_WORDS; other roles show their own name
CANNOT_TELL = [
    "An idle run with no summary.json: finished badly, crashed, or inside one long step with no log growing. The map says only how long nothing was written.",
    "In the role_usage mode (no trace): whether a visit passed, is read from where the run went next; a retry of the same stage because a reviewer asked for changes looks the same as a gate failure, and a route back caused by a design request looks the same as one caused by a gate.",
    "The role working now: role_usage rows are written when a role's call ends, so the map shows the last role that reported in this visit, not one that is mid-call.",
    "A Vivado slot wait is shown only while the last slot_wait row is under 5 minutes old and the build step is open; an older one cannot be told from a build that is just running.",
    "Gates passed in the role_usage mode: ledger_entry rows record failing gates only, so a passing gate is not an event there (the stage's leave row says it was left forward).",
]


def machine(run_limits: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The stages from the stage machine: number, name, the gates its exit check needs, the stages a failure may route to, and its visit limit for this run."""
    from agent.graph.stages import MACHINE, RUN_LIMITS, visit_limit
    lim = dict(RUN_LIMITS)
    if isinstance(run_limits, dict) and isinstance(run_limits.get("visits_per_stage"), int):
        lim["visits_per_stage"] = run_limits["visits_per_stage"]
    return [{"n": s.n, "name": s.name, "gates": list(s.gates), "loops_to": list(s.loops_to), "limit": visit_limit(s.n, lim)} for s in MACHINE]


def _first_fail(items: list[str]) -> str | None:
    """The name of the first failing gate of a gates call: items look like 'post_synth: post_synth_no_unconstrained_endpoints' or 'lint'."""
    for it in items:
        s = str(it).split(":")[-1].strip()
        if s:
            return redact.text(s)[:60]
    return None


def _ledger(rd: Path) -> list[dict[str, Any]]:
    return [r for r in PG._rows(rd / "routing_events.jsonl") if r.get("event") == "ledger_entry"]


def _pending(rd: Path) -> dict[str, Any] | None:
    try:
        p = json.loads((rd / "pending.json").read_text()).get("paused")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(p, dict) or not isinstance(p.get("kind"), str):
        return None
    kind = p["kind"]
    why = {"review": "paused for your review", "question": "waiting for your answer to a question", "permission": "waiting for your permission", "paused": "paused at your request"}.get(kind, "waiting for you")
    if kind == "permission" and p.get("needs"):
        why += ": " + ", ".join(str(x)[:40] for x in list(p["needs"])[:6])
    return {"kind": kind[:20], "reason": redact.text(why)[:200], "stage": p.get("stage") if isinstance(p.get("stage"), int) else None}


def _trace_events(rd: Path, names: dict[str, int], audit_p: Path | None) -> list[dict[str, Any]] | None:
    """Events of the trace mode, in time order; None when the trace has no stage_start (the role_usage mode takes over)."""
    ev = [t for t in PG._rows(rd / "trace.jsonl") if t.get("kind") == "event" and isinstance(t.get("t"), (int, float))]
    if not any(e.get("event") == "stage_start" and e.get("stage") in names for e in ev):
        return None
    out: list[dict[str, Any]] = []
    seq = 0

    def put(t: float, kind: str, **f: Any) -> None:
        nonlocal seq
        seq += 1
        out.append({"t": float(t), "_o": seq, "kind": kind, **f})

    for e in ev:
        st, t = e.get("stage"), e["t"]
        n = names.get(st) if isinstance(st, str) else None
        name = e.get("event")
        if name == "stage_start" and n is not None:
            put(t, "enter", n=n, visit=e.get("visit") if isinstance(e.get("visit"), int) else None)
        elif name == "stage_end" and n is not None:
            put(t, "leave", n=n, visit=e.get("visit") if isinstance(e.get("visit"), int) else None, ok=bool(e.get("passed")))
        elif name == "build_step":
            put(t, "step", n=n, state="start" if e.get("state") == "start" else "end", what=f"Vivado {redact.text(str(e.get('until') or ''))[:12]} build".replace("  ", " "),
                ok=e.get("ok") if isinstance(e.get("ok"), bool) else None)
        elif name == "console":
            put(t, "step", n=n, state="start", what=redact.text(str(e.get("label") or "tool"))[:60], step_id=str(e.get("step"))[:60])
        elif name == "console_end":
            put(t, "step", n=n, state="end", what="", step_id=str(e.get("step"))[:60])
        elif name == "slot_wait":
            put(t, "wait", n=n, why="waiting for a Vivado slot (" + redact.text(str(e.get("reason") or ""))[:80] + f"); waited {int(e.get('waited_s') or 0)} s", wait="slot")
        elif name == "permission_stop":
            put(t, "wait", n=e.get("n") if isinstance(e.get("n"), int) else n, why="permission needed: " + ", ".join(str(x)[:40] for x in list(e.get("needs") or [])[:6]), wait="permission")
        elif name == "permission_granted":
            put(t, "resume", n=e.get("n") if isinstance(e.get("n"), int) else n, why="permission granted: " + ", ".join(str(x)[:40] for x in list(e.get("actions") or [])[:6]))
        elif name == "request":
            what, outcome = str(e.get("what") or "")[:20], str(e.get("outcome") or "")[:20]
            if what == "pause" and outcome == "applied":
                put(t, "wait", n=n, why="paused at your request", wait="paused")
            elif what == "pause" and outcome == "done":
                put(t, "resume", n=n, why="resumed after your pause request")
            else:
                put(t, "request", n=n, what=what, outcome=outcome, to_stage=e.get("to_stage") if isinstance(e.get("to_stage"), int) else None)
    if audit_p is not None:
        for a in PG._rows(audit_p):
            if a.get("tool") != "gates" or not isinstance(a.get("t"), (int, float)):
                continue
            g = PG.parse_gates(str(a.get("result_summary") or ""))
            if g:
                put(a["t"], "gate", n=names.get(a.get("stage")) if isinstance(a.get("stage"), str) else None, ok=g["verdict"] == "PASS", failing=g["failing"], numbers=g["numbers"], design=g["design"])
    out.sort(key=lambda r: (r["t"], r["_o"]))
    # roles carry no time: right after the stage entry of their (stage, visit), in file order
    roles: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for u in PG._rows(rd / "role_usage.jsonl"):
        if isinstance(u.get("stage"), str) and u["stage"] in names and isinstance(u.get("visit"), int) and isinstance(u.get("role"), str):
            roles.setdefault((names[u["stage"]], u["visit"]), []).append(u)
    merged: list[dict[str, Any]] = []
    for r in out:
        merged.append(r)
        if r["kind"] == "enter":
            for u in roles.get((r["n"], r["visit"]), []):
                merged.append({"t": r["t"], "kind": "role", "n": r["n"], "visit": r["visit"], "role": u["role"][:20], "repair": bool(u.get("repair")), "turns": u.get("turns") if isinstance(u.get("turns"), int) else None})
    return merged


def _usage_events(rd: Path, names: dict[str, int], summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Events of the role_usage mode: one enter per (stage, visit) in file order, its role rows, its failing gates (ledger), then a leave read from where the run went next."""
    rows = [u for u in PG._rows(rd / "role_usage.jsonl") if isinstance(u.get("stage"), str) and u["stage"] in names and isinstance(u.get("visit"), int) and isinstance(u.get("role"), str)]
    ledger: dict[tuple[int, int], list[str]] = {}
    for l in _ledger(rd):
        if isinstance(l.get("stage"), str) and l["stage"] in names and isinstance(l.get("visit"), int):
            ledger.setdefault((names[l["stage"]], l["visit"]), []).extend(str(g) for g in (l.get("gates") or []))
    order: list[tuple[int, int]] = []
    for u in rows:
        k = (names[u["stage"]], u["visit"])
        if k not in order:
            order.append(k)
    out: list[dict[str, Any]] = []
    stop = summary.get("stop") if isinstance(summary, dict) and isinstance(summary.get("stop"), str) else None
    for i, (n, v) in enumerate(order):
        out.append({"kind": "enter", "n": n, "visit": v})
        for u in rows:
            if (names[u["stage"]], u["visit"]) == (n, v):
                out.append({"kind": "role", "n": n, "visit": v, "role": u["role"][:20], "repair": bool(u.get("repair")), "turns": u.get("turns") if isinstance(u.get("turns"), int) else None})
        fails = ledger.get((n, v), [])
        if fails:
            out.append({"kind": "gate", "n": n, "ok": False, "failing": [redact.text(str(g))[:60] for g in fails[:12]], "numbers": "", "design": ""})
        if i + 1 < len(order):
            out.append({"kind": "leave", "n": n, "visit": v, "ok": order[i + 1][0] > n, "inferred": True})
        elif stop is not None:
            out.append({"kind": "leave", "n": n, "visit": v, "ok": stop == "done", "inferred": True})
    return out


def _fold(events: list[dict[str, Any]], mach: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    """Add what the page needs to each event: its plain sentence, the route-back it caused, and the state of every stage after it."""
    nst = len(mach)
    st = [{"v": 0, "res": None, "gp": 0, "gf": 0} for _ in range(nst)]
    cur: int | None = None
    role: str | None = None
    step: dict[str, Any] | None = None
    wait: dict[str, Any] | None = None
    last_fail: dict[int, str] = {}                              # the failing gate last seen at each stage
    prev_enter: int | None = None
    open_: bool = False                                           # the current stage's visit has begun and its end is not recorded yet
    prev: dict[str, Any] | None = None
    frames: list[dict[str, Any]] = []

    def nm(n: int | None) -> str:
        return f"stage {n} ({mach[n]['name']})" if n is not None and 0 <= n < nst else "a stage"

    for i, e in enumerate(events):
        k, n = e["kind"], e.get("n")
        f: dict[str, Any] = {"i": i, "kind": k, "n": n, "t": e.get("t")}
        line = ""
        if k == "enter":
            st[n]["v"] = e["visit"] if isinstance(e.get("visit"), int) else st[n]["v"] + 1       # the run's own visit number (brief 234 resets the counts a route back passes again)
            f.update(visit=st[n]["v"], limit=mach[n]["limit"], from_n=prev_enter)
            if prev_enter is not None and n < prev_enter:
                gate = last_fail.get(prev_enter)
                by_request = prev is not None and prev["kind"] == "request" and prev.get("outcome") == "rewind"
                f.update(back=True, route=(f"your request: back to stage {n}" if by_request else f"{gate or 'failing gate not recorded'}: back to stage {n}"))
                line = f"{nm(n)}, visit {st[n]['v']} of {mach[n]['limit']}: route back from stage {prev_enter} ({f['route']})"
            elif prev_enter is not None and n == prev_enter:
                gate = last_fail.get(n)
                f.update(retry=True, route=f"{gate or 'failing gate not recorded'}: again")
                line = f"{nm(n)}, visit {st[n]['v']} of {mach[n]['limit']}: the stage runs again ({f['route']})"
            else:
                line = f"{nm(n)}, visit {st[n]['v']} of {mach[n]['limit']}: entered" + (f" from stage {prev_enter}" if prev_enter is not None else "")
            cur, prev_enter, role, step, wait, open_ = n, n, None, None, None, True
        elif k == "role":
            role = e["role"]
            f.update(role=role, name=ROLE_NAMES.get(role, role), repair=e.get("repair"), turns=e.get("turns"))
            line = f"{ROLE_NAMES.get(role, role)} reported" + (" (a repair call)" if e.get("repair") else "") + f" in {nm(n)}"
            if n is not None:
                cur = n
        elif k == "gate":
            if n is None:
                n = cur
                f["n"] = n
            if n is not None:
                st[n]["gp" if e["ok"] else "gf"] += 1
            f.update(ok=e["ok"], failing=e.get("failing") or [], numbers=e.get("numbers") or "", flash="pass" if e["ok"] else "fail")
            if not e["ok"] and n is not None:
                g = _first_fail(e.get("failing") or [])
                if g:
                    last_fail[n] = g
            line = f"Gates at {nm(n)}: " + ("pass" if e["ok"] else "FAIL" + (": " + "; ".join(f["failing"][:3]) if f["failing"] else ""))
        elif k == "leave":
            if n is not None:
                st[n]["res"] = "pass" if e["ok"] else "fail"
            f.update(ok=e["ok"], inferred=bool(e.get("inferred")))
            line = f"{nm(n)} {'passed its gate' if e['ok'] else 'did not pass its gate'}" + (" (read from where the run went next)" if e.get("inferred") else "")
            step, open_ = None, False
        elif k == "step":
            if e["state"] == "start":
                step = {"what": e.get("what") or "a tool", "id": e.get("step_id")}
                line = f"Tool running at {nm(n if n is not None else cur)}: {step['what']}"
            else:
                step = None
                wait = None if wait and wait.get("kind") == "slot" else wait
                line = "Tool step ended" + ("" if e.get("ok") is None else (" (ok)" if e["ok"] else " (failed)"))
            f.update(state=e["state"], what=e.get("what") or "")
        elif k == "wait":
            wait = {"kind": e.get("wait") or "waiting", "why": e["why"], "t": e.get("t")}
            line = e["why"][:200]
        elif k == "resume":
            wait = None
            line = e["why"][:200]
        elif k == "request":
            line = f"Request at {nm(n)}: {e.get('what')} ({e.get('outcome')})"
            f.update(what=e.get("what"), outcome=e.get("outcome"))
        elif k == "end":
            f.update(ok=e["ok"], stop=e["stop"])
            step, wait, open_ = None, None, False
            line = "Run ended: " + e["stop"]
        f["line"] = redact.text(line)
        f.update(cur=cur, open=open_, role=role, step=dict(step) if step else None, wait=dict(wait) if wait else None, st=[[x["v"], x["res"], x["gp"], x["gf"]] for x in st])
        frames.append(f)
        prev = e
    return frames


def stage_map(runs_dir: Path, run_id: str, now: float | None = None) -> dict[str, Any] | None:
    p = PG.run_progress(runs_dir, run_id, tail=1, now=now)
    if p is None:
        return None
    now = time.time() if now is None else now
    rd = Path(runs_dir) / run_id
    cfg = PG._json(rd / "config.json") or {}
    mach = machine(cfg.get("run_limits") if isinstance(cfg.get("run_limits"), dict) else None)
    names = {m["name"]: m["n"] for m in mach}
    summary = PG._json(rd / "summary.json")
    audit_p = PG._audit_file(rd, cfg.get("name") if isinstance(cfg.get("name"), str) else None)
    events = _trace_events(rd, names, audit_p)
    mode = "trace"
    if events is None:
        mode, events = "role_usage", _usage_events(rd, names, summary if isinstance(summary, dict) else None)
    finished = isinstance(summary, dict)
    if finished:
        stop = summary.get("stop") if isinstance(summary.get("stop"), str) else "stop reason not recorded"
        events.append({"kind": "end", "n": None, "stop": redact.text(stop)[:300], "ok": stop == "done"})
    else:
        pend = _pending(rd)
        if pend is not None:
            events.append({"kind": "wait", "n": pend["stage"], "why": pend["reason"], "wait": pend["kind"]})
    frames = _fold(events, mach, mode)
    # a slot wait older than the window, with no later event, is not shown as a wait (cannot be told from a build that is running)
    if frames and not finished and frames[-1].get("wait") and frames[-1]["wait"].get("kind") == "slot" and now - float(frames[-1]["wait"].get("t") or 0) > SLOT_WAIT_RECENT_S:
        frames[-1]["wait"] = None
    cut = max(0, len(frames) - MAX_FRAMES)
    files = ["config.json", "role_usage.jsonl", "summary.json", "pending.json"] + (["trace.jsonl", "<design>/build/audit.jsonl"] if mode == "trace" else ["routing_events.jsonl"])
    return {"id": run_id, "status": p["status"], "age_s": p["last_write_age_s"], "active_s": PG.ACTIVE_S, "stop": p["stop"], "machine": mach, "frames": frames[cut:], "dropped_frames": cut,
            "can_replay": finished and len(frames) > 1,
            "source": {"mode": mode, "dir": f"runs/{run_id}/", "files": files,
                       "note": ("Events come from trace.jsonl, the audit log and role_usage.jsonl." if mode == "trace" else
                                "This folder has no trace.jsonl, so the events come from the order of the role_usage.jsonl rows and the ledger rows of routing_events.jsonl; whether a stage passed is read from where the run went next. These rows carry no times.")},
            "cannot_tell": CANNOT_TELL}
