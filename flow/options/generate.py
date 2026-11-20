"""The options generator (brief 104): one model step with a fixed output schema, checked by code.

``improve`` classifies the request (``schema.classify_request``: no model call for an ambiguous or unsupported one), shows the model the
analysis (``view``: the facts with ids, never file contents), takes its JSON reply, checks it (``schema.check_options``), gives it one repair
round with the problems listed, and returns the record the run keeps: the request, the analysis hash, the options offered, what was rejected and
why, and the model's identity (purpose, endpoint, model, table hash). Prompt text is in the private knowledge repository (brief 99): this file
holds only data and the names of the prompts; the record keeps their hashes.

The model is called through the resolver (brief 108): ``llm`` is ``Resolver.text("options")``, or any ``(system, user) -> text`` for a test.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from typing import Any

from agent.core import managed, prompts
from flow.options import combine, schema

PROMPTS = {"system": "graph/options/system", "user": "graph/options/user", "repair": "graph/options/repair"}
RECORD_SCHEMA = "fda-strategy-record/1"


def view(analysis: dict[str, Any], *, blind: bool = False) -> dict[str, Any]:
    """What the model sees: components, latency stages, timing, resources, crossings and the citable facts (id, value, unit, text, origin).
    No file names or hashes (the check maps ids to files), and, when ``blind``, no technique or removable-clocks hints from the stage file."""
    lat = analysis.get("latency")
    stages = None
    if lat:
        stages = []
        for s in lat["stages"]:
            d = {k: s[k] for k in ("id", "name", "domain", "kind", "clocks", "ns", "component", "setup_slack_ns", "why", "risk_of_removing")}
            if not blind:
                d["technique"] = s["technique"]
                d["removable_clocks"] = s["removable_clocks"]
            stages.append(d)
    facts = [{"id": f["id"], "value": f["value"], "unit": f["unit"], "text": f["text"], "origin": f["origin"]}
             for f in analysis["facts"].values() if not (blind and f["id"].endswith(".removable"))]
    cdc = [r for r in ((analysis.get("cdc") or {}).get("rows") or []) if r["source_clock"] != r["dest_clock"] and r["type"] != "Safely Timed"]
    comps = [{k: c[k] for k in ("name", "ownership", "level", "module", "instance", "aliases", "description", "files", "contract_declared")} for c in analysis["components"]]
    return {"design": analysis["design"], "components": comps,
            "latency": ({"path": lat["path"], "title": lat["title"], "period_ns": lat["period_ns"], "total_clocks": lat["total_clocks"], "reconciled": lat["reconciled"],
                         "stages": stages, "board": lat.get("board"), "note": lat["note"]} if lat else None),
            "timing": analysis.get("timing"), "resources": analysis.get("resources"), "clock_crossings": cdc or None,
            "facts": facts, "gaps": analysis["gaps"], "notes": analysis["notes"]}


def _json_of(text: str) -> Any:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            t = t[i:j + 1]
    return json.loads(t)


def _fill(tmpl: str, **kw: str) -> str:
    for k, v in kw.items():
        tmpl = tmpl.replace(f"<<{k}>>", v)
    return tmpl


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def improve(analysis: dict[str, Any], request: str, project: managed.Project | None, llm: Callable[[str, str], str] | None, *, blind: bool = False,
            mode: str = "new", previous: list[dict[str, Any]] | None = None, edit: dict[str, str] | None = None, max_repairs: int = 1,
            model_info: dict[str, Any] | None = None, prompt_root: Any = None, combiner: bool = True) -> dict[str, Any]:
    """The strategy record for ``request``. ``mode`` is ``new``, ``more`` (different options from ``previous``) or ``edit`` (``edit`` =
    {id, instruction}: the user's change to one previous option). A question comes back as ``status: question`` with no model call when the
    request cannot be served."""
    t0 = time.time()
    rec: dict[str, Any] = {"schema": RECORD_SCHEMA, "request": request, "mode": mode, "blind": blind, "analysis_hash": analysis["hash"],
                           "analysis_sources": analysis["sources"], "options_schema": schema.SCHEMA, "model": model_info or {}, "attempts": 0, "prompts": {},
                           "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    cls = schema.classify_request(request, project, analysis)
    if cls["status"] == "question":
        return {**rec, "status": "question", "question": cls["question"], "reason": cls["reason"], "options": [], "rejected": [], "notes": [], "goal": None}
    goal, pinned = cls["goal"], cls["pinned"]
    rec["goal"] = goal
    if llm is None:
        raise RuntimeError("no model call is available for the options purpose")
    kw = {"root": prompt_root} if prompt_root is not None else {}
    system = prompts.load(PROMPTS["system"], **kw)
    user_t = prompts.load(PROMPTS["user"], **kw)
    repair_t = prompts.load(PROMPTS["repair"], **kw)
    rec["prompts"] = {k: {"name": v, "sha256": _sha(prompts.load(v, **kw))} for k, v in PROMPTS.items()}
    payload = {"request": request, "goal": goal, "scope_pinned_to": pinned or None, "mode": mode,
               "previous_options": [{"id": o["id"], "title": o["title"], "scope": o["scope"]["components"], "touches_stages": o["touches_stages"]} for o in (previous or [])] or None,
               "user_edit": edit, "min_options": 1 if mode == "edit" else schema.MIN_OPTIONS, "max_options": 1 if mode == "edit" else schema.MAX_OPTIONS,
               "analysis": view(analysis, blind=blind)}
    user = _fill(user_t, payload=json.dumps(payload, indent=1, default=str))
    reply = ""
    result: dict[str, Any] = {}
    for attempt in range(1 + max_repairs):
        rec["attempts"] = attempt + 1
        u = user if attempt == 0 else _fill(repair_t, problems="\n".join(f"- {p}" for p in result.get("repairable", [])), previous_reply=reply[:6000], payload=json.dumps(payload, indent=1, default=str))
        reply = llm(system, u)
        try:
            doc = _json_of(reply)
        except ValueError:
            result = {"status": "invalid", "options": [], "rejected": [], "notes": ["the reply was not JSON"], "repairable": ["the reply must be one JSON object and nothing else"], "question": None}
            continue
        result = schema.check_options(doc, analysis, project, goal=goal, pinned=pinned, blind=blind, min_options=payload["min_options"])
        if result["status"] == "question" or not result["repairable"]:
            break
    status = result["status"]
    if status == "invalid":
        status = "failed"
    rec.update(status=status, question=result.get("question"), options=result["options"], rejected=result["rejected"], notes=result["notes"],
               unresolved=result.get("repairable") if result["status"] != "question" else [], wall_s=round(time.time() - t0, 1))
    if mode == "edit" and edit and status == "options" and result["options"]:
        result["options"][0]["id"] = edit["id"]
    if combiner and mode == "new" and status == "options" and rec["options"]:      # brief 104A/104B: code splits bundles into per-stage parts, then builds the cumulative options
        combine.apply(rec, analysis, project, goal=goal, pinned=pinned, blind=blind)
    rec["options_hash"] = _sha(json.dumps(rec["options"], sort_keys=True))
    return rec
