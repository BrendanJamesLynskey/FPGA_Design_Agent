"""Mid-run requests (brief 182): a user's request to a running agent, applied only at a safe point.

A request is one of two kinds:

- **control**: ``pause`` (wait at the next safe point; resume with ``python -m agent resume <run_id> --reply '{"resume": true}'``), ``stop_after N`` (end the run once stage N has
  passed), ``abort`` (end the run at the next safe point);
- **design**: free text, such as "use block RAM for the FIFO". It reaches the next stage's writer as the owner's note; when its words name an earlier
  stage (the pickup classifier, ``agent.graph.pickup.classify_change``) the run is rewound to that stage through the snapshot rewind and the note goes there.

``<run_dir>/requests.jsonl`` is append-only: one row per event (``queued``, ``accepted``, ``applied``, ``done``, ``declined``) and :func:`load` folds the rows
into one record per request. The agent applies a request at a **safe point**: the start of ``node_advance``, which is the end of a stage after its gate and its
review (so also right after a review interrupt is answered). Never in the middle of a tool call or a model turn. Each applied request is a user intervention in
``build/who_did_what.json`` and counted in the run's ``summary.json``.

A scored run (its ``config.json`` names a hidden spec, or its directory holds a ``SCORED`` file) refuses design requests: a user's design note would make the score
not comparable. Control requests stay allowed.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

FILE = "requests.jsonl"
SCORED_MARKER = "SCORED"
CONTROL = ("pause", "stop_after", "abort")
MAX_TEXT = 500
ID = re.compile(r"^r\d{3}$")
STATES = ("queued", "accepted", "applied", "done", "declined")
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class RequestError(ValueError):
    """The request was refused before it was queued; the message is the reason shown to the user."""


# --- the run's mode -----------------------------------------------------------------------------------------------------------

def eval_mode(run_dir: Path) -> dict[str, Any]:
    """``{"scored": bool, "held_out": bool, "why": str}``. Scored: a hidden spec in config.json, or a SCORED file. Held out: the hidden spec is under benchmark_private/."""
    run_dir = Path(run_dir)
    why, held = "", False
    try:
        c = json.loads((run_dir / "config.json").read_text())
    except (OSError, ValueError):
        c = {}
    hs = c.get("hidden_spec")
    if hs not in (None, "", "None"):
        why = "the run has a hidden spec (a benchmark or evaluation run)"
        held = "benchmark_private" in str(hs) or "held" in str(hs).lower()
    if (run_dir / SCORED_MARKER).exists():
        why = why or "the run directory holds a SCORED marker"
    return {"scored": bool(why), "held_out": held, "why": why}


def has_ended(run_dir: Path) -> bool:
    """A run has ended when its summary.json exists and is not the record of a pause (brief 219 fix 7: a run paused for the programming
    approval writes a summary marked ``paused`` and can still take requests at the next safe point)."""
    f = Path(run_dir) / "summary.json"
    if not f.is_file():
        return False
    try:
        return not json.loads(f.read_text()).get("paused")
    except (OSError, ValueError, AttributeError):
        return True


# --- the file -----------------------------------------------------------------------------------------------------------------

def _scrub(s: str) -> str:
    try:
        from agent.core.security import redact
        return redact(s)
    except Exception:                                   # noqa: BLE001
        return s


def _append(run_dir: Path, row: dict[str, Any]) -> None:
    with (Path(run_dir) / FILE).open("a") as f:
        f.write(json.dumps({"t": round(time.time(), 1), "when": time.strftime("%Y-%m-%d %H:%M:%S"), **row}) + "\n")


def load(run_dir: Path) -> list[dict[str, Any]]:
    """One record per request: the queued row's fields, the latest ``status``, ``reason`` and the history of events."""
    out: dict[str, dict[str, Any]] = {}
    try:
        lines = (Path(run_dir) / FILE).read_text().splitlines()
    except OSError:
        return []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(r, dict) or not ID.match(str(r.get("id", ""))):
            continue
        cur = out.setdefault(r["id"], {"id": r["id"], "history": []})
        for k, v in r.items():
            if k not in ("event", "t", "when"):
                cur[k] = v
        cur["status"] = r.get("event", cur.get("status"))
        cur["history"].append({"event": r.get("event"), "when": r.get("when"), "reason": r.get("reason", "")})
    return list(out.values())


def pending(run_dir: Path) -> list[dict[str, Any]]:
    return [r for r in load(run_dir) if r.get("status") in ("queued",)]


def counts(run_dir: Path) -> dict[str, Any]:
    rs = load(run_dir)
    qa = 0
    try:
        qa = sum(1 for ln in (Path(run_dir) / "qa.jsonl").read_text().splitlines() if ln.strip())
    except OSError:
        pass
    return {"control": sum(1 for r in rs if r.get("kind") == "control"), "design": sum(1 for r in rs if r.get("kind") == "design"),
            "applied": sum(1 for r in rs if r.get("status") in ("applied", "done")), "declined": sum(1 for r in rs if r.get("status") == "declined"),
            "questions_asked": qa, "user_interventions": sum(1 for r in rs if r.get("status") in ("accepted", "applied", "done"))}


def describe(r: dict[str, Any]) -> str:
    if r.get("kind") == "design":
        return "design request: " + str(r.get("text", ""))[:120]
    a = r.get("action")
    return {"pause": "pause at the next safe point", "abort": "abort at the next safe point", "stop_after": f"stop after stage {r.get('stage')}"}.get(a, str(a))


# --- queueing -----------------------------------------------------------------------------------------------------------------

def submit(run_dir: Path, *, control: str | None = None, stage: int | None = None, design: str | None = None, source: str = "cli",
           next_stage: str | None = None, stages: tuple[str, ...] = ()) -> dict[str, Any]:
    """Queue one request. Raises :class:`RequestError` with the reason when it must be refused. ``next_stage`` and ``stages`` only word the acknowledgement."""
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise RequestError("no such run directory")
    if (control is None) == (design is None):
        raise RequestError("give exactly one of a control request and a design request")
    if has_ended(run_dir):
        raise RequestError("the run has ended (its summary.json exists): there is no safe point left to apply a request at")
    rec: dict[str, Any] = {"source": source}
    if control is not None:
        action = control.replace("-", "_")
        if action not in CONTROL:
            raise RequestError(f"control must be one of {', '.join(CONTROL)}")
        if action == "stop_after":
            if isinstance(stage, bool) or not isinstance(stage, int) or not (0 <= stage <= 9):
                raise RequestError("stop-after needs a stage number from 0 to 9")
            rec.update(stage=stage)
        elif stage is not None:
            raise RequestError(f"{action} takes no stage")
        rec.update(kind="control", action=action)
        when = "at the next safe point (the end of the stage that is running now, after its gate and review)"
        affects = (f"the run ends after stage {stage} passes" if action == "stop_after" else "the whole run (it waits for a resume)" if action == "pause" else "the whole run (it ends)")
    else:
        em = eval_mode(run_dir)
        if em["scored"]:
            raise RequestError(f"design requests are refused for a scored run ({em['why']}); control requests are still allowed")
        t = CTRL.sub(" ", design or "").strip()
        if not t:
            raise RequestError("the request text is empty")
        if len(t) > MAX_TEXT:
            raise RequestError(f"the request text is at most {MAX_TEXT} characters")
        if t.startswith("-"):
            raise RequestError("the request text cannot start with '-'")
        rec.update(kind="design", text=_scrub(t))
        from agent.graph.pickup import classify_change
        k, s, words = classify_change(t)
        when = "at the next safe point (the end of the stage that is running now)"
        if words and s is not None:
            nm = stages[s] if 0 <= s < len(stages) else str(s)
            affects = f"if the run is already past stage {s} ({nm}) it is rewound to it; otherwise the next stage's writer gets it (matched: {', '.join(w for w in words if not w.startswith('('))[:60]})"
        else:
            affects = "the next stage's writer gets it as the owner's note" + (f" ({next_stage})" if next_stage else "")
    n = 1 + max((int(r["id"][1:]) for r in load(run_dir)), default=0)
    rec.update(id=f"r{n:03d}", applies=when, affects=affects)
    _append(run_dir, {"event": "queued", **rec})
    return next(r for r in load(run_dir) if r["id"] == rec["id"])


# --- the safe point -----------------------------------------------------------------------------------------------------------

def _stage_names() -> tuple[str, ...]:
    from agent.core.session import STAGES
    return tuple(STAGES)


def safe_point(rt: Any, state: dict, advance: Any) -> dict[str, Any]:
    """Called by ``node_advance``. ``advance(rt, n, state)`` is the node's own next-stage rule. Returns the state update.

    Order: (1) a pause waits here, before anything else is applied, so that a resume (which runs this node again) loses nothing;
    (2) the stop-after requests set the run's stop stage; (3) the stage machine's own rule; (4) abort; (5) design requests."""
    run_dir, n = Path(rt.run_dir), state["stage"]
    names = _stage_names()
    rs = load(run_dir)
    for r in rs:                                         # a resumed process rebuilds its config from config.json: apply every accepted stop-after again
        if r.get("kind") == "control" and r.get("action") == "stop_after" and r.get("status") in ("accepted", "done") and isinstance(r.get("stage"), int):
            rt.cfg.stop_after = r["stage"] if rt.cfg.stop_after is None else min(rt.cfg.stop_after, r["stage"])
    waiting = [r for r in rs if r.get("kind") == "control" and r.get("action") == "pause" and r.get("status") in ("queued", "applied")]
    if waiting:
        r = waiting[0]
        if r["status"] == "queued":
            _intervene(rt, r, f"paused at the end of stage {n} ({names[n]})")
            _append(run_dir, {"event": "applied", "id": r["id"], "reason": f"paused at the end of stage {n} ({names[n]}); resume with: python -m agent resume {rt.run_id} --reply '{{\"resume\": true}}'"})
            _event(rt, "request", names[n], request=r["id"], what="pause", outcome="applied")
        from langgraph.types import interrupt
        interrupt({"kind": "paused", "reason": "user request", "id": r["id"], "stage": n, "stage_name": names[n], "resume": f"python -m agent resume {rt.run_id} --reply '{{\"resume\": true}}'"})
        _append(run_dir, {"event": "done", "id": r["id"], "reason": "resumed"})
        _event(rt, "request", names[n], request=r["id"], what="pause", outcome="done")
        rs = load(run_dir)
    queued = [r for r in rs if r.get("status") == "queued"]
    for r in queued:
        if r["kind"] == "control" and r["action"] == "stop_after":
            if r["stage"] < n:
                _decline(rt, r, f"stage {r['stage']} had already passed when the request reached a safe point (the run is at stage {n})")
                continue
            rt.cfg.stop_after = r["stage"] if rt.cfg.stop_after is None else min(rt.cfg.stop_after, r["stage"])
            _intervene(rt, r, f"stop after stage {r['stage']}")
            _append(run_dir, {"event": "accepted", "id": r["id"], "reason": f"the run ends when stage {r['stage']} ({names[r['stage']]}) passes"})
            _event(rt, "request", names[n], request=r["id"], what="stop_after", outcome="accepted")
    upd = advance(rt, n, state)
    for r in queued:
        if r["kind"] == "control" and r["action"] == "abort":
            _intervene(rt, r, "abort")
            _append(run_dir, {"event": "done", "id": r["id"], "reason": f"the run ended at the end of stage {n} ({names[n]}) on request"})
            _event(rt, "request", names[n], request=r["id"], what="abort", outcome="done")
            return {"stop": "aborted: user request"}
    for r in queued:
        if r["kind"] == "design":
            upd = _apply_design(rt, r, upd, n, names)
    for r in load(run_dir):                              # a stop-after request is done when the run ends because of it
        if r.get("action") == "stop_after" and r.get("status") == "accepted" and upd.get("stop"):
            _append(run_dir, {"event": "done", "id": r["id"], "reason": f"the run ended after stage {r['stage']} passed"})
    return upd


def _apply_design(rt: Any, r: dict, upd: dict, n: int, names: tuple[str, ...]) -> dict:
    run_dir = Path(rt.run_dir)
    em = eval_mode(run_dir)
    if em["scored"]:
        _decline(rt, r, f"declined: this run is scored ({em['why']})")
        return upd
    if upd.get("stop"):
        _decline(rt, r, f"the run ended ({upd['stop']}) before the next stage could take the request")
        return upd
    nxt = upd.get("stage", n)
    from agent.graph.pickup import classify_change
    _, s, words = classify_change(r.get("text", ""))
    note_text = "User request (mid-run, applied at the end of stage %d): %s" % (n, r["text"])
    _intervene(rt, r, f"design request: {r['text'][:120]}")
    if words and s is not None and s < nxt:
        try:
            res = rt.snaps.rewind(s)
        except Exception as e:                           # noqa: BLE001 (no snapshot for that stage)
            res = {"verified": False, "error": str(e)[:100]}
        if res.get("verified"):
            _append(run_dir, {"event": "done", "id": r["id"], "reason": f"rewound to stage {s} ({names[s]}) through the snapshot rewind; the request goes to that stage's writer as the owner's note"})
            _event(rt, "request", names[n], request=r["id"], what="design", outcome="rewind", to_stage=s)
            from agent.graph import ownership
            ownership.record(rt.design, "owner", names[n], f"rewound to stage {s} (request {r['id']})", r["text"][:200], n=n)
            return {**upd, "stage": s, "note": note_text, "note_role": "", "fails": [], "evidence": {}, "hand_edit_only": False}
        _append(run_dir, {"event": "accepted", "id": r["id"], "reason": f"the rewind to stage {s} could not be done ({res.get('error') or 'files not verified'}); the request goes to stage {nxt} ({names[nxt]}) instead"})
    prev = upd.get("note") or ""
    _append(run_dir, {"event": "done", "id": r["id"], "reason": f"given to stage {nxt} ({names[nxt]}) as the owner's note"})
    _event(rt, "request", names[n], request=r["id"], what="design", outcome="note", to_stage=nxt)
    return {**upd, "note": (prev + "\n" if prev else "") + note_text}


def _decline(rt: Any, r: dict, why: str) -> None:
    _append(Path(rt.run_dir), {"event": "declined", "id": r["id"], "reason": why})
    _event(rt, "request", None, request=r["id"], what=r.get("action") or "design", outcome="declined")


def _intervene(rt: Any, r: dict, what: str) -> None:
    from agent.graph import ownership
    try:
        ownership.record(rt.design, "owner", rt.session.stage or "", "mid-run request", f"{r['id']}: {what}"[:300])
    except Exception:                                    # noqa: BLE001 (the ledger is a record, never a reason to stop)
        pass


def _event(rt: Any, name: str, stage: str | None, **f: Any) -> None:
    try:
        from agent.core.trace import Trace
        Trace(Path(rt.run_dir) / "trace.jsonl", harness="graph").event(name, stage, **f)
    except Exception:                                    # noqa: BLE001
        pass
