"""A run's plain-words status (brief 182): what it has done, what it is doing, what is next, what is blocked or waiting, and the cost against the cap.

Derived by code from the run's own records, **no model call**: ``role_usage.jsonl``, ``snapshots.json``, ``trace.jsonl`` (its ``kind: "event"`` rows: stage start
and end, a build step, a slot wait, a console pointer, a request outcome), ``requests.jsonl``, ``qa.jsonl``, ``pending.json`` and ``summary.json``. Nothing is
started and nothing is written. The text is rebuilt when a stage ends, when a request changes, or after ``FDA_STATUS_MIN`` minutes (default 5); the structured fields
(the step running now and its elapsed time, the cost) are always current.

Field names avoid the words ``redact.scrub`` drops (text, question, answer, reply, message ...): the page receives exactly what is built here.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from navigator import progress as PG
from navigator import redact

REFRESH_MIN = float(os.environ.get("FDA_STATUS_MIN", "5") or 5)
SLOT_WAIT_RECENT_S = 300
_memo: dict[str, tuple[tuple, float, str]] = {}


def _mins(s: float | None) -> str:
    if s is None:
        return "an unknown time"
    return f"{round(s)} s" if s < 90 else f"{round(s / 60)} min" if s < 5400 else f"{s / 3600:.1f} h"


def _usd(x: Any) -> str:
    return "n/a" if x is None else f"${float(x):.2f}"


def _events(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in trace if t.get("kind") == "event"]


def _pending(rd: Path) -> dict[str, Any] | None:
    """The interrupt a paused run is waiting on (written by the CLI when it stops for an answer): kind, stage, and for a question its text and default."""
    try:
        p = json.loads((rd / "pending.json").read_text()).get("paused")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(p, dict):
        return None
    out: dict[str, Any] = {"kind": str(p.get("kind"))[:20], "stage": p.get("stage") if isinstance(p.get("stage"), int) else None, "stage_name": p.get("stage_name") if isinstance(p.get("stage_name"), str) else None}
    if p.get("kind") == "question":
        out.update(qid=str(p.get("id"))[:12], ask=redact.text(str(p.get("question") or ""))[:400], default=redact.text(str(p.get("default") or ""))[:200], why=redact.text(str(p.get("reason") or ""))[:300])
    if p.get("kind") == "paused":
        out.update(resume=str(p.get("resume") or "")[:120])
    return out


def _requests(rd: Path) -> list[dict[str, Any]]:
    from agent.graph import requests as rq
    out = []
    for r in rq.load(rd)[-30:]:
        out.append({"id": r["id"], "kind": r.get("kind"), "action": r.get("action"), "stage": r.get("stage"), "what": redact.text(str(r.get("text") or ""))[:300], "status": r.get("status"),
                    "applies": r.get("applies"), "affects": r.get("affects"), "source": r.get("source"), "label": rq.describe(r),
                    "reason": redact.text(str((r.get("history") or [{}])[-1].get("reason") or ""))[:300], "when": (r.get("history") or [{}])[0].get("when")})
    return out


def summarise(runs_dir: Path, run_id: str, now: float | None = None) -> dict[str, Any] | None:
    from agent.core.session import STAGES
    now = time.time() if now is None else now
    p = PG.run_progress(runs_dir, run_id, tail=1, now=now)
    if p is None:
        return None
    rd = Path(runs_dir) / run_id
    ev = _events(PG._rows(rd / "trace.jsonl"))
    starts = [e for e in ev if e.get("event") == "stage_start"]
    ends = [e for e in ev if e.get("event") == "stage_end"]
    reqs = _requests(rd)
    pend = _pending(rd)
    cur = p["stage"]
    n = p["stage_n"]
    # what has been done: the last outcome of each stage from the stage_end events, else the snapshots
    outcome: dict[str, bool | None] = {}
    for e in ends:
        if isinstance(e.get("stage"), str):
            outcome[e["stage"]] = bool(e.get("passed"))
    if not outcome:
        for d in p["stages_done"]:
            if isinstance(d.get("stage"), str):
                outcome[d["stage"]] = True
    passed = [s for s in STAGES if outcome.get(s) is True]
    failed = [s for s in STAGES if outcome.get(s) is False and s != cur]
    # the step running now: a console step without its end row, a build step without its end
    open_console = None
    ended = {e.get("step") for e in ev if e.get("event") == "console_end"}
    for e in ev:
        if e.get("event") == "console" and e.get("step") not in ended:
            open_console = e
    build_open = None
    for e in ev:
        if e.get("event") == "build_step":
            build_open = e if e.get("state") == "start" else None
    step = None
    if p["status"] != "finished" and open_console is not None and isinstance(open_console.get("started"), (int, float)):
        since = max(0.0, now - float(open_console["started"]))
        step = {"label": str(open_console.get("label")), "since_s": round(since), "step": open_console.get("step"), "source": open_console.get("source")}
    slot = None
    for e in reversed(ev):
        if e.get("event") == "slot_wait":
            slot = e if isinstance(e.get("t"), (int, float)) and now - e["t"] < SLOT_WAIT_RECENT_S and (build_open is not None) else None
            break
    blocked: list[str] = []
    if slot is not None:
        blocked.append(f"waiting for a Vivado slot ({slot.get('reason')}); waited {_mins(slot.get('waited_s'))} so far")
    if pend is not None:
        if pend["kind"] == "review":
            blocked.append(f"paused for your review after stage {pend['stage']} ({pend.get('stage_name')}): approve, edit or rewind with python -m agent resume {run_id}")
        elif pend["kind"] == "question":
            blocked.append("waiting for your answer to a question the agent asked (shown below with its default)")
        elif pend["kind"] == "paused":
            blocked.append(f"paused at your request after stage {pend['stage']} ({pend.get('stage_name')}): {pend.get('resume')}")
    queued = [r for r in reqs if r["status"] == "queued"]
    if queued:
        blocked.append(f"{len(queued)} request{'s' if len(queued) != 1 else ''} queued, to be applied at the next safe point (the end of this stage)")
    if p["status"] == "idle" and pend is None and p["last_write_age_s"] is not None:
        blocked.append(f"no record written for {_mins(p['last_write_age_s'])}: the run has stopped, crashed or is in one long step")
    # doing / next
    visit = p["visit"]
    if p["status"] == "finished":
        doing = f"finished: {p['stop'] or 'stop reason not recorded'}"
        nxt = "nothing: the run has ended"
    elif pend is not None:
        doing = "waiting"
        nxt = {"review": "the next stage after you answer", "question": "the stage that asked, once you answer", "paused": "the next stage after a resume"}.get(pend["kind"], "the next stage after you answer")
    elif cur is None:
        doing = "starting"
        nxt = "stage 0 (clarify)"
    else:
        bits = [f"stage {n} ({cur})" + (f", visit {visit}" if visit else "")]
        if p["role"]:
            bits.append(f"role {p['role']}")
        if step:
            bits.append(f"{step['label']} for {_mins(step['since_s'])}")
        elif build_open is not None:
            bits.append(f"Vivado {build_open.get('until')} build, started {_mins(now - build_open['t']) if isinstance(build_open.get('t'), (int, float)) else 'recently'} ago")
        doing = ", ".join(bits)
        nxt = (f"stage {n + 1} ({STAGES[n + 1]}) if the gate passes; a failure sends the run back to the stage that owns it" if n is not None and n + 1 < len(STAGES)
               else "the end of the run when the gate passes")
    c = p["cost"]
    cost = f"{_usd(c['reported_usd'])} provider-reported of a {_usd(c['budget_usd'])} cap" if c["budget_usd"] else f"{_usd(c['reported_usd'])} provider-reported (no cap recorded)"
    if c["plan_estimate_usd"]:
        cost += f"; {_usd(c['plan_estimate_usd'])} plan estimate (Claude Code on the subscription, not a bill)"
    done_txt = (f"{len(passed)} of {len(STAGES)} stages passed" + (": " + ", ".join(f"{STAGES.index(s)} {s}" for s in passed) if passed else "")) if passed else "no stage has passed yet"
    if failed:
        done_txt += f"; stage{'s' if len(failed) > 1 else ''} {', '.join(str(STAGES.index(s)) for s in failed)} failed its gate at least once and ran again"
    ev_key = (len(ends), len(starts), tuple((r["id"], r["status"]) for r in reqs), p["status"], pend and pend["kind"], bool(slot))
    memo = _memo.get(run_id)
    text = None
    if memo and memo[0] == ev_key and now - memo[1] < REFRESH_MIN * 60:
        text, built = memo[2], memo[1]
    else:
        built = now
        text = f"{done_txt}. Doing now: {doing}. Next: {nxt}. " + (("Blocked or waiting: " + "; ".join(blocked) + ". ") if blocked else "Nothing is blocked. ") + "Cost: " + cost + "."
        if len(_memo) > 64:
            _memo.clear()
        _memo[run_id] = (ev_key, built, text)
    return {"id": run_id, "status": p["status"], "sentence": text, "built_at": built, "refresh_min": REFRESH_MIN, "done": done_txt, "doing": doing, "next": nxt, "blocked": blocked,
            "cost_line": cost, "step": step, "stage": cur, "requests": reqs, "pending": pend, "mode": _mode(rd), "qa_count": _qa_count(rd),
            "note": "Built from the run's records by code, with no model call; the page asks again every 5 s and the sentence changes when a stage ends, a request changes or every "
                    f"{REFRESH_MIN:g} min."}


def _mode(rd: Path) -> dict[str, Any]:
    from agent.graph import requests as rq
    return rq.eval_mode(rd)


def _qa_count(rd: Path) -> int:
    try:
        return sum(1 for ln in (rd / "qa.jsonl").read_text().splitlines() if ln.strip())
    except OSError:
        return 0
