"""The live console's reader (brief 182): the output of whatever a run is doing now, as the browser may see it.

The agent writes each step's output to ``<run_dir>/console/<step>.log`` while the step runs (the Claude Code stream, Vivado's log, the simulator's or the formal
tool's output, test runs) and names it in the run's ``trace.jsonl`` with a ``console`` event (``agent/core/console.py``). This module lists those steps and reads
them incrementally. **The caller names a step id from the list built here, never a path**; the path comes from the run's own trace and is checked to lie inside the
run's ``console/`` or ``claude_code/`` directory and not be a link. Reads go from a byte offset and return at most 256 KB (the last 256 KB when the first read is of a
larger file) and only whole lines while the step is still running. Every line passes ``redact.text`` and the response passes ``redact.scrub`` in the server.

What is shown: the model's streamed output (assistant text, and each tool call with its arguments summarised) and tool output. **Never a prompt**: a prompt is not in
these files, and a record of one is only ever a name and a hash. For a **scored or held-out run** the console shows tool names and progress lines only: no assistant
text, no tool arguments, and from a tool's output only its progress lines (a count says how many lines were withheld).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from navigator import progress as PG
from navigator import redact

MAX_BYTES = 256 * 1024
STEP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
PROGRESS = re.compile(r"^(INFO: \[(Common|Synth|Route|Place|Vivado)|Starting |Phase |Finished |Ending |Running |synth_design|opt_design|place_design|route_design|write_bitstream|Time \(s\)|"
                      r"# |\*{3} |PASS|FAIL|TESTS=|tests? (passed|failed)|Elapsed|Total |\[\d+/\d+\])", re.I)


def _safe_file(rd: Path, rel: str) -> Path | None:
    """The file named by a trace row, only when it lies in console/ or claude_code/ of the run and is a plain file."""
    if not isinstance(rel, str) or "\x00" in rel or rel.startswith("/") or ".." in Path(rel).parts or Path(rel).parts[:1] not in (("console",), ("claude_code",)):
        return None
    p = rd / rel
    try:
        if p.is_symlink() or not p.is_file() or rd.resolve() not in p.resolve().parents:
            return None
    except OSError:
        return None
    return p


def steps(runs_dir: Path, run_id: str, now: float | None = None) -> dict[str, Any] | None:
    """The list the browser picks from: ``{"steps": [{id, label, kind, started, seconds, active, size, source}], "restricted": bool}``, newest last."""
    if not PG.RUN_ID.match(run_id):
        return None
    rd = Path(runs_dir) / run_id
    if not rd.is_dir() or rd.is_symlink():
        return None
    now = time.time() if now is None else now
    from agent.graph import requests as rq
    mode = rq.eval_mode(rd)
    trace = PG._rows(rd / "trace.jsonl")
    ends = {e.get("step"): e for e in trace if e.get("kind") == "event" and e.get("event") == "console_end"}
    finished = (rd / "summary.json").is_file()
    out: list[dict[str, Any]] = []
    seen = set()
    for e in trace:
        if e.get("kind") == "event" and e.get("event") == "console" and isinstance(e.get("step"), str) and STEP_ID.match(e["step"]) and e["step"] not in seen:
            f = _safe_file(rd, str(e.get("source")))
            if f is None:
                continue
            seen.add(e["step"])
            end = ends.get(e["step"])
            out.append({"id": e["step"], "label": str(e.get("label"))[:60], "kind": str(e.get("kind"))[:20], "stage": e.get("stage"), "started": e.get("started"),
                        "seconds": end.get("seconds") if end else None, "active": end is None and not finished and bool(f.stat().st_size >= 0) and now - f.stat().st_mtime < 3600,
                        "size": f.stat().st_size, "source": str(e.get("source"))})
    for f in sorted((rd / "claude_code").glob("*.jsonl")) if (rd / "claude_code").is_dir() else []:      # runs from before the live console: the finished stream of each model call
        sid = "cc-" + f.stem
        if sid not in seen and STEP_ID.match(sid) and _safe_file(rd, f"claude_code/{f.name}") is not None:
            out.append({"id": sid, "label": "model: " + f.stem.split("_", 2)[1] if "_" in f.stem else "model", "kind": "claude_stream", "stage": None, "started": f.stat().st_mtime, "seconds": None,
                        "active": False, "size": f.stat().st_size, "source": f"claude_code/{f.name}"})
    return {"id": run_id, "steps": out[-200:], "restricted": mode["scored"], "held_out": mode["held_out"],
            "restriction": ("scored or held-out run: tool names and progress lines only, no model text" if mode["scored"] else None),
            "note": "Output is read from the run's console files as it is written; prompts are never shown (names and hashes only)."}


def _summarise_args(a: Any) -> str:
    if isinstance(a, dict):
        parts = []
        for k, v in list(a.items())[:4]:
            sv = v if isinstance(v, (int, float, bool)) or v is None else str(v).replace("\n", " ")
            parts.append(f"{k}={sv if not isinstance(sv, str) else (sv[:60] + ('...' if len(sv) > 60 else ''))}")
        return ", ".join(parts) + (", ..." if len(a) > 4 else "")
    return str(a)[:80]


def render_stream_line(raw: str, restricted: bool) -> list[str]:
    """One stream-json line of a Claude Code call as readable lines. Restricted: tool names and turn markers only."""
    try:
        o = json.loads(raw)
    except ValueError:
        return [] if restricted else [raw[:300]]
    if not isinstance(o, dict):
        return []
    t = o.get("type")
    out: list[str] = []
    if t == "assistant":
        for b in ((o.get("message") or {}).get("content") or []):
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and not restricted:
                out += [("assistant: " if i == 0 else "  ") + ln for i, ln in enumerate(str(b.get("text") or "").splitlines()[:30])]
            elif b.get("type") == "tool_use":
                name = str(b.get("name") or "?").replace("mcp__fda__", "")
                out.append(f"tool call: {name}" + ("" if restricted else f"({_summarise_args(b.get('input'))})"))
    elif t == "user" and not restricted:
        for b in ((o.get("message") or {}).get("content") or []):
            if isinstance(b, dict) and b.get("type") == "tool_result":
                c = b.get("content")
                c = " ".join(str(x.get("text", "")) for x in c if isinstance(x, dict)) if isinstance(c, list) else str(c)
                first = (c.strip().splitlines() or [""])[0]
                out.append("  tool result: " + first[:200])
    elif t == "result":
        out.append(f"finished: {o.get('subtype')}, {o.get('num_turns')} turns" + ("" if restricted else ""))
    return out


def read(runs_dir: Path, run_id: str, step: str, offset: int | None = None, now: float | None = None) -> dict[str, Any] | None:
    """Incremental read of one step. ``offset`` None: the last 256 KB. Returns ``{lines, next_offset, size, active, withheld, ...}`` or None for an unknown run or step."""
    listing = steps(runs_dir, run_id, now)
    if listing is None or not isinstance(step, str) or not STEP_ID.match(step):
        return None
    st = next((s for s in listing["steps"] if s["id"] == step), None)
    if st is None:
        return None
    rd = Path(runs_dir) / run_id
    f = _safe_file(rd, st["source"])
    if f is None:
        return None
    size = f.stat().st_size
    start = 0 if offset is None else max(0, int(offset))
    first = offset is None or start > size
    if first or size - start > MAX_BYTES:
        start = max(0, size - MAX_BYTES)
    with f.open("rb") as fh:
        fh.seek(start)
        data = fh.read(min(MAX_BYTES, size - start)) if size > start else b""
    skipped = False
    if start > 0 and (first or size - (offset or 0) > MAX_BYTES) and data:           # a tail: drop the partial first line
        cut = data.find(b"\n")
        data, start, skipped = (data[cut + 1:], start + cut + 1, True) if cut >= 0 else (b"", start + len(data), True)
    if st["active"] and data and not data.endswith(b"\n"):                          # a running step: hold back the line still being written
        cut = data.rfind(b"\n")
        data = data[:cut + 1] if cut >= 0 else b""
    nxt = start + len(data)
    restricted = listing["restricted"]
    lines: list[str] = []
    withheld = 0
    for ln in data.decode("utf-8", "replace").splitlines():
        if st["kind"] == "claude_stream":
            lines += render_stream_line(ln, restricted)
        elif restricted and not PROGRESS.search(ln):
            withheld += 1
        else:
            lines.append(ln[:400])
    return {"id": run_id, "step": step, "label": st["label"], "kind": st["kind"], "source": st["source"], "started": st["started"], "active": st["active"],
            "size": size, "offset": start, "next_offset": nxt, "tail_only": skipped or (start > 0 and offset is None), "lines": [redact.text(x) for x in lines], "withheld": withheld,
            "restricted": restricted}
