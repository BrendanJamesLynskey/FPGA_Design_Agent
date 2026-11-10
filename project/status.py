"""``project status``: for every module and stage, whether its evidence is current, stale, failing or missing.

Evidence lives in ``modules/<m>/evidence/status.json`` (format below). Each item records the stage key
(:func:`project.stages.stage_keys`) of the inputs it was made from. An item is **current** only when that key equals
the key computed from today's files; nothing else is trusted, and the dashboard reads only this result.

    {"schema": "fpga-design-agent/evidence/v1", "module": "<m>", "provenance": "hand-written" | "flow",
     "items": [{"stage": "<stage name>", "kind": "approval" | "contract_test" | "verification" | "ooc_timing" |
                "resources" | "hil" | "gates", "result": "pass" | "fail" | "not-run", "key": "<64 hex>", ...}]}

Kind-specific fields (all optional): ``by`` and ``note`` (approval); ``v_level`` (verification); ``clock``,
``target_mhz`` and ``wns_ns`` (ooc_timing); ``lut``, ``ff``, ``bram_tile``, ``dsp`` (resources); ``source``, the
committed file the numbers come from. ``provenance: hand-written`` marks evidence nobody measured (the P0 example);
the status output and the dashboard say so wherever it is shown.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent.core.session import STAGES
from project.schema import Project, check_project
from project.stages import stage_index, stage_keys

EVIDENCE_SCHEMA = "fpga-design-agent/evidence/v1"
KINDS = ("approval", "contract_test", "verification", "ooc_timing", "resources", "hil", "gates")
RESULTS = ("pass", "fail", "not-run")
PROVENANCE = ("hand-written", "flow")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def check_evidence(ev: Any, module: str) -> list[str]:
    if not isinstance(ev, dict):
        return ["status.json must be a JSON object"]
    e = []
    if ev.get("schema") != EVIDENCE_SCHEMA:
        e.append(f"schema must be {EVIDENCE_SCHEMA!r}")
    if ev.get("module") != module:
        e.append(f"module = {ev.get('module')!r}, expected {module!r}")
    if ev.get("provenance") not in PROVENANCE:
        e.append(f"provenance must be one of {', '.join(PROVENANCE)}")
    if not isinstance(ev.get("items"), list):
        return e + ["'items' must be a list"]
    for i, it in enumerate(ev["items"]):
        if not isinstance(it, dict):
            e.append(f"items[{i}] must be an object")
            continue
        if stage_index(it.get("stage")) is None:
            e.append(f"items[{i}]: stage {it.get('stage')!r} is not one of {', '.join(STAGES)}")
        if it.get("kind") not in KINDS:
            e.append(f"items[{i}]: kind must be one of {', '.join(KINDS)}")
        if it.get("result") not in RESULTS:
            e.append(f"items[{i}]: result must be one of {', '.join(RESULTS)}")
        if not _HEX64.match(str(it.get("key", ""))):
            e.append(f"items[{i}]: key must be the 64-hex stage key (python -m project hash)")
    return e


def load_evidence(project: Project, module: str) -> tuple[dict[str, Any] | None, list[str]]:
    p = project.root / "modules" / module / "evidence" / "status.json"
    if not p.is_file():
        return None, []
    try:
        ev = json.loads(p.read_text())
    except ValueError as x:
        return None, [f"modules/{module}/evidence/status.json is not valid JSON: {x}"]
    errs = check_evidence(ev, module)
    return (ev if not errs else None), [f"modules/{module}/evidence/status.json: {x}" for x in errs]


def stage_state(items: list[dict[str, Any]]) -> str:
    """none | stale | fail | not-run | pass, for one stage's items (each already marked ``current``)."""
    if not items:
        return "none"
    if any(not it["current"] for it in items):
        return "stale"
    if any(it.get("result") == "fail" for it in items):
        return "fail"
    if any(it.get("result") == "not-run" for it in items):
        return "not-run"
    return "pass"


def module_status(project: Project, module: str) -> dict[str, Any]:
    keys = stage_keys(project, module)
    ev, errs = load_evidence(project, module)
    stages = []
    for k in keys:
        items = []
        for it in (ev or {}).get("items") or []:
            if stage_index(it.get("stage")) == k["n"]:
                items.append({**it, "current": it.get("key") == k["key"]})
        stages.append({"n": k["n"], "stage": k["stage"], "key": k["key"], "state": stage_state(items), "items": items})
    reached = -1
    for s in stages:
        if s["state"] != "pass":
            break
        reached = s["n"]
    stale = [s["n"] for s in stages if s["state"] == "stale"]
    first_open = next((s["n"] for s in stages if s["state"] != "pass"), None)
    m = project.module(module)
    return {"module": module, "kind": m.get("kind"), "reached": reached,
            "reached_stage": STAGES[reached] if reached >= 0 else None,
            "reentry": min(stale) if stale else first_open,
            "reentry_why": "stale evidence" if stale else ("first stage without passing evidence" if first_open is not None
                                                           else None),
            "provenance": (ev or {}).get("provenance"), "evidence_errors": errs, "stages": stages}


def project_status(root: Path) -> dict[str, Any]:
    p = check_project(Path(root))
    mods = [module_status(p, m) for m in p.modules() if m in p.contracts] if not _fatal(p) else []
    errors = list(p.errors) + [x for m in mods for x in m["evidence_errors"]]
    return {"schema": "fpga-design-agent/project-status/v1", "project": p.design.get("name"),
            "board": p.design.get("board"), "valid": not errors, "errors": errors, "warnings": p.warnings,
            "hand_written": sorted({m["module"] for m in mods if m["provenance"] == "hand-written"}),
            "modules": mods,
            "connections": [x for x in p.design.get("connections") or [] if isinstance(x, dict)],
            "domains": {m: {"clocks": p.module(m).get("clocks")} for m in p.contracts},
            "assumptions_open": [a for a in p.design.get("assumptions") or []
                                 if isinstance(a, dict) and a.get("status", "open") == "open"],
            "stages": list(STAGES)}


def _fatal(p: Project) -> bool:
    return not p.design or not p.contracts


def text(st: dict[str, Any]) -> str:
    """The plain-text table the CLI prints."""
    out = [f"project {st['project']} (board {st['board']}): {'valid' if st['valid'] else 'INVALID'}"]
    out += [f"  error: {e}" for e in st["errors"]]
    out += [f"  warning: {w}" for w in st["warnings"]]
    if st["hand_written"]:
        out.append(f"  NOTE: evidence of {', '.join(st['hand_written'])} is hand-written (provenance), not measured")
    short = {"none": "-", "stale": "STALE", "fail": "FAIL", "not-run": "n/r", "pass": "pass"}
    head = "  module        " + " ".join(f"{n:>5}" for n in range(len(st["stages"]))) + "   reached / re-enter at"
    out.append(head)
    for m in st["modules"]:
        cells = " ".join(f"{short[s['state']]:>5}" for s in m["stages"])
        re_ = "-" if m["reentry"] is None else f"{m['reentry']} {st['stages'][m['reentry']]} ({m['reentry_why']})"
        out.append(f"  {m['module']:<13} {cells}   {m['reached']} / {re_}")
    out.append("  stages: " + ", ".join(f"{i} {n}" for i, n in enumerate(st["stages"])))
    for a in st["assumptions_open"]:
        out.append(f"  open assumption {a.get('id')}: {a.get('text')} (default: {a.get('default')})")
    return "\n".join(out)
