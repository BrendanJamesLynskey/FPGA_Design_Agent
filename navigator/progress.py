"""Live progress of an agent run, read from the run directory only: the same for a run the navigator started and one started from the CLI.

Files read (all written by the agent while it runs): ``config.json`` (the budget), ``role_usage.jsonl`` (one row per sub-agent visit: stage, visit, role, tokens,
the plan's cost estimate), ``trace.jsonl`` (model and tool rows; the provider-reported cost of each model call), ``snapshots.json`` (one entry per finished stage),
``<design>/build/audit.jsonl`` (every tool call the agent made, with the gate results) and ``summary.json`` (written once, when the run ends). Nothing is
started and nothing is written. Only named fields are copied out; the audit tail shows the tool, stage, result flag and the first line of the result summary.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from navigator import redact

RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
ACTIVE_S = 180                      # a file written within this many seconds: the run is working
READ_LIMIT = 6_000_000              # a log larger than this is read from its last 6 MB only (the rows are then a tail, and the page says so)
GATE_LINE = re.compile(r"^gates: (\S+) \((\w+)\): (PASS|FAIL)\s*(.*)$")
STAGE_LINE = re.compile(r"^  ([\w-]+): (pass|FAIL|fail)\s*$")
GATE_ITEM = re.compile(r"^    (ok  |FAIL|fail|warn)\s+(\S+)")
_cache: dict[tuple[str, int, int], Any] = {}


def _rows(p: Path) -> list[dict[str, Any]]:
    try:
        st = p.stat()
    except OSError:
        return []
    key = (str(p), st.st_mtime_ns, st.st_size)
    if key in _cache:
        return _cache[key]
    rows: list[dict[str, Any]] = []
    if True:
        try:
            with p.open() as f:
                if st.st_size > READ_LIMIT:
                    f.seek(st.st_size - READ_LIMIT)
                    f.readline()                          # drop the partial first line
                for line in f:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(r, dict):
                        rows.append(r)
        except OSError:
            return []
    if len(_cache) > 64:
        _cache.clear()
    _cache[key] = rows
    return rows


def _json(p: Path) -> Any:
    try:
        if p.stat().st_size > 8_000_000:
            return None
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _audit_file(rd: Path, name: str | None) -> Path | None:
    cands = [rd / name / "build" / "audit.jsonl"] if name and RUN_ID.match(name) else []
    cands += sorted(rd.glob("*/build/audit.jsonl"))
    for c in cands:
        if c.is_file():
            return c
    return None


def parse_gates(summary: str) -> dict[str, Any] | None:
    """The result of one ``gates`` tool call: the overall verdict, per-stage pass/fail and the failing items, from the tool's own text."""
    lines = (summary or "").splitlines()
    head = next((GATE_LINE.match(ln) for ln in lines if GATE_LINE.match(ln)), None)
    if not head:
        return None
    stages: dict[str, str] = {}
    failing: list[str] = []
    cur = None
    for ln in lines:
        m = STAGE_LINE.match(ln)
        if m:
            cur = m.group(1)
            stages[cur] = m.group(2).lower()
            continue
        g = GATE_ITEM.match(ln)
        if g and g.group(1).strip() in ("FAIL", "fail"):
            failing.append(f"{cur}: {g.group(2)}" if cur else g.group(2))
    return {"design": head.group(1), "variant": head.group(2), "verdict": head.group(3), "numbers": redact.brief(head.group(4), 140), "stages": stages, "failing": failing[:12]}


def run_progress(runs_dir: Path, run_id: str, tail: int = 40, now: float | None = None) -> dict[str, Any] | None:
    if not RUN_ID.match(run_id):
        return None
    rd = Path(runs_dir) / run_id
    if not rd.is_dir() or rd.is_symlink():
        return None
    now = time.time() if now is None else now
    cfg = _json(rd / "config.json") or {}
    limits = cfg.get("run_limits") if isinstance(cfg.get("run_limits"), dict) else {}
    usage = _rows(rd / "role_usage.jsonl")
    trace = _rows(rd / "trace.jsonl")
    summary = _json(rd / "summary.json")
    audit_p = _audit_file(rd, cfg.get("name") if isinstance(cfg.get("name"), str) else None)
    audit = _rows(audit_p) if audit_p else []
    from agent.core.session import STAGES
    # stage, visit: the last sub-agent visit that wrote a row; visits per stage: the highest visit seen
    visits: dict[str, int] = {}
    for u in usage:
        if isinstance(u.get("stage"), str) and isinstance(u.get("visit"), int):
            visits[u["stage"]] = max(visits.get(u["stage"], 0), u["visit"])
    last = usage[-1] if usage else {}
    cur_stage = last.get("stage") or next((t.get("stage") for t in reversed(trace) if t.get("stage")), None) or next((a.get("stage") for a in reversed(audit) if a.get("stage")), None)
    # cost: provider-reported (numeric cost_usd of the trace's model rows) apart from the plan's estimate (Claude Code on the subscription)
    reported = sum(_num(t.get("cost_usd")) or 0.0 for t in trace if t.get("kind") == "model")
    unreported = sum(1 for t in trace if t.get("kind") == "model" and _num(t.get("cost_usd")) is None)
    estimate = sum(_num(u.get("plan_cost_estimate_usd")) or 0.0 for u in usage)
    tokens = sum(int(u["tokens"]) for u in usage if isinstance(u.get("tokens"), int))
    budget = _num(limits.get("usd"))
    # gate results: every gates call in the audit log, newest last
    gates = []
    for a in audit:
        if a.get("tool") == "gates":
            g = parse_gates(str(a.get("result_summary") or ""))
            if g:
                g.update(stage=a.get("stage"), at=a.get("t"))
                gates.append(g)
    snaps = _json(rd / "snapshots.json")
    done = [{"n": s.get("n"), "stage": s.get("stage")} for s in snaps if isinstance(s, dict)] if isinstance(snaps, list) else []
    mt = [p.stat().st_mtime for p in (rd / "role_usage.jsonl", rd / "trace.jsonl", rd / "claude_code_calls.jsonl", rd / "model_calls.jsonl", audit_p) if p is not None and p.is_file()]
    last_write = max(mt) if mt else None
    age = None if last_write is None else max(0.0, now - last_write)
    if isinstance(summary, dict):
        status = "finished"
    elif age is not None and age <= ACTIVE_S:
        status = "active"
    else:
        status = "idle"
    tail_rows = []
    for a in audit[-max(1, min(tail, 200)):]:
        first = str(a.get("result_summary") or "").strip().splitlines()
        tail_rows.append({"t": _num(a.get("t")), "tool": str(a.get("tool"))[:40], "stage": a.get("stage") if isinstance(a.get("stage"), str) else None,
                          "ok": a.get("ok") if isinstance(a.get("ok"), bool) else None, "refused": a.get("refused") if isinstance(a.get("refused"), bool) else None,
                          "line": redact.brief(first[0], 160) if first else ""})
    return {"id": run_id, "name": cfg.get("name") if isinstance(cfg.get("name"), str) else None, "status": status, "last_write_age_s": None if age is None else round(age),
            "stop": summary.get("stop") if isinstance(summary, dict) and isinstance(summary.get("stop"), str) else None,
            "stage": cur_stage, "stage_n": STAGES.index(cur_stage) if cur_stage in STAGES else None, "stages": list(STAGES), "visit": last.get("visit") if isinstance(last.get("visit"), int) else None,
            "visits": visits, "role": last.get("role") if isinstance(last.get("role"), str) else None, "stages_done": done,
            "cost": {"reported_usd": round(reported, 4), "reported_calls_without_cost": unreported, "plan_estimate_usd": round(estimate, 4), "budget_usd": budget,
                     "note": "reported: the provider's own figure; plan estimate: Claude Code on the subscription (an estimate, not a bill); the budget is the run's own cap on the reported figure"},
            "tokens": tokens, "model_rows": sum(1 for t in trace if t.get("kind") == "model"), "tool_rows": sum(1 for t in trace if t.get("kind") == "tool"),
            "harness": cfg.get("harness") if isinstance(cfg.get("harness"), str) else None, "cc_model": cfg.get("cc_model") if isinstance(cfg.get("cc_model"), str) else None,
            "gates": gates[-8:], "audit_tail": tail_rows, "audit_rows": len(audit),
            "source": {"dir": f"runs/{run_id}/", "files": ["config.json", "role_usage.jsonl", "trace.jsonl", "snapshots.json", "<design>/build/audit.jsonl", "summary.json"]}}


def run_ids(runs_dir: Path, limit: int = 40) -> list[str]:
    """Run directories, newest name first (a run id starts with its start time): those with a config.json."""
    d = Path(runs_dir)
    if not d.is_dir():
        return []
    ids = sorted((p.name for p in d.iterdir() if p.is_dir() and not p.is_symlink() and RUN_ID.match(p.name) and (p / "config.json").is_file()), reverse=True)
    return ids[:limit]


def live_list(runs_dir: Path, limit: int = 30, now: float | None = None) -> list[dict[str, Any]]:
    out = []
    for rid in run_ids(runs_dir, limit):
        p = run_progress(runs_dir, rid, tail=1, now=now)
        if p:
            out.append({k: p[k] for k in ("id", "name", "status", "last_write_age_s", "stage", "visit", "cost", "harness", "cc_model", "stop")})
    return out
