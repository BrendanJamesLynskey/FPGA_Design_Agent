"""Agent tools that make latency a skill (brief 97): ``latency_path`` (every register and clock crossing on the wire-to-wire chain, per
direction, in clocks and ns, reconciled against the benches, with the post-route slack of each stage's registers when a
checkpoint has been read) and ``latency_budget`` (the table to reason from: stage, clocks, ns, why it exists, what removing it risks,
what could come out, and the board's share that simulation cannot see).

Both read the design's ``latency_stages.yaml``; neither takes a path, a command or a board. ``refresh`` re-runs the design's own
whole-core bench (the pytest entry the stage file names) for fresh clocks; without it the last recorded clocks are used and the
answer says which. A design without a stage file is refused with the reason. Two different "critical paths": the timing-critical
path (worst slack) limits the clock period; the latency-critical path is this chain (registers x period).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.core.registry import tool
from agent.core.session import Session
from flow.latency import model as lm

PATH_ARG = {"type": "string", "enum": ["tick_to_trade", "echo"], "description": "which chain: the trading path or the echo (default tick_to_trade)"}
REFRESH = {"type": "boolean", "description": "re-run the design's whole-core bench for fresh clocks (about a minute; simulation only)"}


def _inputs(s: Session, refresh: bool) -> tuple[dict[str, Any], dict[str, Any], dict | None, dict | None, str]:
    st = lm.load_stages(s.design)
    if refresh:
        core = lm.run_trace(s.design, st, out=s.design / "build" / "latency" / "core_sim.json", root=s.root)
        src = f"fresh bench run ({core.name})"
    else:
        cached = s.design / "build" / "latency" / "core_sim.json"
        core = cached if cached.is_file() else s.root / st["trace"]["results_file"]
        src = f"recorded clocks ({core.relative_to(s.root) if s.root in core.parents else core.name})"
    sl_file = s.root / st["slack"]["file"]
    cached_sl = s.design / "build" / "latency" / "latency_slack.json"
    slack = lm.load_slack(cached_sl if cached_sl.is_file() else sl_file)
    return st, json.loads(Path(core).read_text()), slack, None, src


def _fmt_path(r: dict[str, Any]) -> str:
    lines = [f"{r['title']}", f"period {r['period_ns']} ns; total {r['total_clocks']} clocks = {r['total_ns']} ns; reconciled with the bench: {r['reconciled']}"]
    for x in r["stages"]:
        sl = (x["netlist"] or {}).get("setup_slack_ns")
        lines.append(f"  {x['cumulative_clocks'] if x['cumulative_clocks'] is not None else '-':>3} {x['id']:<16} {x['domain']:<6} +{x['clocks']} clk "
                     f"{x['ns']} ns" + (f"  slack {sl} ns" + (" [timing-critical]" if x["timing_critical"] else "") if sl is not None else ""))
    lines += [f"  WARNING (the stage file no longer matches the bench; the design changed since it was written, trust the bench's total): {p}" for p in r["problems"]]
    return "\n".join(lines)


@tool("latency_path", "List every register and clock crossing on the design's wire-to-wire latency chain, per direction, with its clock "
      "domain, the clocks and ns it adds (from the design's whole-core simulation) and, when a post-route checkpoint has been read, the "
      "setup slack of its registers; marks stages that are also timing-critical. Reconciles the stage clocks with the bench and "
      "reports any difference. The latency-critical path (this chain) is not the timing-critical path (worst slack).",
      {"path": PATH_ARG, "refresh": REFRESH})
def latency_path(s: Session, path: str = "tick_to_trade", refresh: bool = False) -> dict:
    try:
        st, core, slack, _, src = _inputs(s, refresh)
        r = lm.latency_path(s.design, core, slack, path, st)
    except lm.LatencyError as e:
        return {"ok": False, "output": f"latency_path: {e}"}
    return {"ok": True, "output": _fmt_path(r) + f"\nclocks from: {src}", "latency_path": r}


@tool("latency_budget", "The latency budget the agent reasons from: each stage of the chain ranked by what could come out, with its clocks, ns, "
      "why it exists, what removing it risks, the technique that removes it, and the board's share (GT, optics, wire-to-wire from the "
      "recorded board run) that simulation cannot see. Digital and board figures are never added into one number: the "
      "unattributed difference is shown. The removable clocks are an upper bound, not a plan.",
      {"path": PATH_ARG, "refresh": REFRESH})
def latency_budget(s: Session, path: str = "tick_to_trade", refresh: bool = False) -> dict:
    try:
        st, core, slack, _, src = _inputs(s, refresh)
        b = lm.latency_budget(s.design, core, slack, s.root / Path(st["slack"]["file"]).parent, st, path)
    except lm.LatencyError as e:
        return {"ok": False, "output": f"latency_budget: {e}"}
    lines = [f"budget for {b['design']} {b['path']}: digital {b['digital_clocks']} clocks = {b['digital_ns']} ns (reconciled: {b['reconciled']}); clocks from: {src}"]
    for r in b["rows"]:
        lines.append(f"  {r['stage']:<16} {r['domain']:<6} {r['clocks']} clk {r['ns']} ns  removable {r['removable_clocks']} via {r['technique']}"
                     + (" [needs board]" if r["needs_board"] else "") + f"\n      why: {r['why_it_exists']}\n      risk: {r['risk_of_removing']}")
    if b.get("board"):
        bd = b["board"]
        lines.append(f"  board: wire-to-wire {bd['wire_to_wire_clocks']} clocks = {bd['wire_to_wire_ns']} ns; GT+optics {bd['gt_optics_clocks']} clocks; "
                     f"unattributed {bd['unattributed_clocks']} clocks")
    lines += [f"  WARNING (stage file out of date): {p}" for p in b["problems"]]
    lines.append(b["note"])
    return {"ok": True, "output": "\n".join(lines), "latency_budget": b}
