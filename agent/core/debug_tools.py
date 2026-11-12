"""Debug tools for the agent (brief 50A): plan a capture, capture on the board, query the capture.

- ``debug_plan``: a structured request (the agent writes it from its own reading of the failure; the schema is
  debug_core/schemas/intent.schema.json) -> a checked plan: probes resolved by RTL name, trigger, window, ports, the
  cuts that would make it fit. Nothing is built. The plan is saved under build/debug/plans/<probeset>.json.
- ``debug_capture``: programs the plan's debug build into SRAM and captures (hardware; stage configuration-and-debug,
  power_ok, hardware budget, board.lock). If no debug build holds the probes it builds one first when ``build`` is true
  (a Vivado run). Returns the plain-words answer, the facts and the capture file's path, never raw samples.
- ``debug_query``: questions to a capture (value_at, first, count, changes, runs, summary, diverge against another
  capture: hardware against simulation).

The plain-English parser (debug_core/request.py) is for people at the command line; the agent gives the intent itself, so
no second model is called from inside a tool and the run's meter sees all spend.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from agent.core.registry import tool
from agent.core.security import SecurityError
from agent.core.session import Session

PY = sys.executable
INTENT_PROPS = {"type": "object", "description": "the request in the intent schema: {probes: [names], trigger: {combine: "
                "AND|OR, conditions: [{signal, op (== != < <= > >= rise fall change), value}]}, pre, post, setup, "
                "stimulus, readback: [{op: write|read|wait_ms, register, value, ms}], question}"}


def _plans(s: Session) -> Path:
    d = s.design / "build" / "debug" / "plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _plan_file(s: Session, probeset: str) -> Path:
    if not probeset.isalnum() or len(probeset) > 32:
        raise SecurityError("arguments", "probeset is the 12-character id debug_plan returned")
    f = _plans(s) / f"{probeset}.json"
    if not f.is_file():
        raise SecurityError("arguments", f"no plan {probeset}; call debug_plan first")
    return f


def _capture_file(s: Session, path: str) -> Path:
    p = (s.design / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    root = (s.design / "build" / "debug").resolve()
    if not p.is_relative_to(root) or p.suffix != ".json":
        raise SecurityError("path", "a capture is a .json file under build/debug/ (as debug_capture returned it)")
    if not p.is_file():
        raise SecurityError("path", f"no capture file {path}")
    return p


@tool("debug_plan", "Plan a logic-analyser capture on the board (vendor ILA, Basic licence tier: one clock domain, at most "
                    "5 probe ports). Give the request as structured intent; signal names are resolved against the RTL "
                    "(registers by hierarchical name, e.g. u_dut.count, or a probes.yaml name); unknown names come back as "
                    "errors with suggestions. Returns the plan in plain words and its probeset id. Builds nothing.",
      {"intent": INTENT_PROPS, "request": {"type": "string", "description": "the request in words, kept for the record"}},
      required=["intent"])
def debug_plan(s: Session, intent: dict, request: str | None = None) -> dict:
    from debug_core.plan import PlanError, make_plan, render
    try:
        plan = make_plan(s.design, intent, request)
    except PlanError as e:
        return {"ok": False, "output": str(e)}
    plan["intent"] = intent
    f = _plans(s) / f"{plan['probeset']}.json"
    f.write_text(json.dumps(plan, indent=1) + "\n")
    return {"ok": not plan["errors"], "output": render(plan), "probeset": plan["probeset"],
            "buildable": not plan["errors"], "errors": plan["errors"], "warnings": plan["warnings"],
            "plan_file": str(f.relative_to(s.design))}


@tool("debug_capture", "Capture on the attached board with a plan from debug_plan: programs the plan's debug ILA build "
                       "(SRAM only), sets up registers, arms, sends the stimulus, uploads, reads the XADC conditions, and "
                       "answers in plain words from the capture. build=true makes the debug build first if none holds the "
                       "probes (a Vivado run of several minutes). Needs stage configuration-and-debug, power_ok and "
                       "hardware budget. Returns the answer, facts and the capture path, not raw samples.",
      {"probeset": {"type": "string"}, "build": {"type": "boolean"}}, required=["probeset"], hardware=True)
def debug_capture(s: Session, probeset: str, build: bool = False) -> dict:
    from flow import hw
    from debug_core import build as B
    if s.stage != "configuration-and-debug":
        raise SecurityError("hardware-stage", f"debug_capture needs the stage configuration-and-debug (now {s.stage})")
    pf = _plan_file(s, probeset)
    plan = json.loads(pf.read_text())
    if plan["errors"]:
        raise SecurityError("arguments", "the plan has errors; fix the request (debug_plan) first")
    try:
        board = hw.load_board(s.board)
    except Exception as e:
        raise SecurityError("hardware-board", f"no usable local board entry ({type(e).__name__}); not touching hardware") from None
    from agent.core.security import EXTRA_SECRETS
    if board.get("cable_serial"):
        EXTRA_SECRETS.add(board["cable_serial"])
    hit = B.find_build(plan)
    out_build: dict[str, Any] = {}
    if hit is None:
        if not build:
            return {"ok": False, "output": f"no debug build holds probe set {probeset}; call again with build=true "
                                           "(a Vivado run) or change the plan to probes an existing debug build has",
                    "needs_build": True}
        ov = B.make_overlay(plan)
        r = s.runner.run("debug_build", [str(s.root / "flow" / "run_vivado.sh"), str(ov), "ila"], s.root, timeout=3600)
        out_build = {"build_returncode": r.returncode}
        hit = B.find_build(plan)
        if hit is None:
            return {"ok": False, "output": f"the debug build failed (exit {r.returncode}): " + (r.stdout + r.stderr)[-3000:],
                    **out_build}
    ov, _ = hit
    p = hw.power_ok(ov / "build" / "ila", s.board)
    if not p["pass"]:
        raise SecurityError("hardware-power", f"power_ok failed for the debug build: {p['why']}; not programming")
    s.hw.charge("debug_capture")
    out = s.design / "build" / "debug" / "runs" / f"agent_{probeset}_{len(list((s.design / 'build' / 'debug').glob('runs/agent_*')))}"
    r = s.runner.run("debug_capture", [PY, "-m", "debug_core", "capture", str(pf), "--board", s.board, "--out", str(out)],
                     s.root, timeout=900)
    cf = out / "capture.json"
    if r.returncode != 0 or not cf.is_file():
        return {"ok": False, "output": (r.stdout + r.stderr)[-4000:], "returncode": r.returncode, **out_build}
    from debug_core import answer as A
    from debug_core import capture as C
    cap = C.load(cf)
    ans = A.answer(cap, plan.get("question"))
    return {"ok": True, "output": ans["text"], "capture": str(cf.relative_to(s.design)),
            "vcd": str((out / "capture.vcd").relative_to(s.design)), "facts": ans["facts"],
            "conditions": {k: cap["conditions"].get(k) for k in ("verdict", "alarms", "outside")},
            "build": {k: cap.get("build", {}).get(k) for k in ("build_id", "probeset")}, **out_build,
            "power_ok": {k: p.get(k) for k in ("pass", "total_w", "junction_c", "source")}}


@tool("debug_query", "Ask a question of a capture without reading its samples: op value_at {channel, cycle}; first "
                     "{channel, cmp, value, from_cycle}; count {channel, cmp, value}; changes {channel, limit}; runs "
                     "{channel, value}; summary; diverge (with other: a second capture of the same probes, e.g. simulation) "
                     "-> the first cycle where they differ. Cycles are relative to the trigger (cycle 0).",
      {"capture": {"type": "string"}, "query": {"type": "object"}, "other": {"type": "string"}}, required=["capture", "query"])
def debug_query(s: Session, capture: str, query: dict, other: str | None = None) -> dict:
    from debug_core import answer as A
    from debug_core import capture as C
    cap = C.load(_capture_file(s, capture))
    oth = C.load(_capture_file(s, other)) if other else None
    res = A.query(cap, query, oth)
    return {"ok": bool(res.get("ok")), "output": json.dumps(res, default=str)[:20000], **{k: v for k, v in res.items() if k != "facts"}}
