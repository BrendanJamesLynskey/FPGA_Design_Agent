"""One build directory (``<design>/build/base``) digested for the closure loop (brief 62A).

``digest_build(d)`` reads ``gates.json`` (the flow's own verdicts and numbers) and the routed reports, and returns::

    {timing: {wns_ns, whs_ns, tns_ns, failing_endpoints, timing_met, period_ns},
     setup_path: <flow.digest.timing record> | None, setup_features: {...}, hold_path: ...,
     utilization: {lut, ff, bram_tile, dsp, iob, carry4, ... and *_available}, util_top: {lut: [...], ff: [...]},
     power: {total_w, dynamic_w, static_w, junction_c, components: {...}, hierarchy: [...]},
     synth: {latches, ram_in_registers, clean}, gates: {name: bool}, files: [reports read]}

``digest_text(dg)`` is the short text the repair prompt gets (a few hundred words at most).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flow.digest import power as pw
from flow.digest import synth, timing, utilization


def _read(d: Path, name: str) -> str:
    p = d / name
    try:
        return p.read_text(errors="replace")
    except OSError:
        return ""


def digest_build(d: Path) -> dict[str, Any]:
    d = Path(d)
    files = []
    try:
        g = json.loads((d / "gates.json").read_text())
        files.append("gates.json")
    except (OSError, ValueError):
        g = {}
    t = g.get("timing") or {}
    out: dict[str, Any] = {"ran": bool(g), "gates": g.get("gates") or {}}
    setup_txt, hold_txt = _read(d, "timing_worst_setup.rpt"), _read(d, "timing_worst_hold.rpt")
    sp = timing.parse_paths(setup_txt)
    hp = timing.parse_paths(hold_txt)
    files += [n for n, x in (("timing_worst_setup.rpt", setup_txt), ("timing_worst_hold.rpt", hold_txt)) if x]
    out["timing"] = {"wns_ns": t.get("wns_ns"), "whs_ns": t.get("whs_ns"), "tns_ns": t.get("tns_ns"),
                     "failing_endpoints": t.get("tns_failing_endpoints"), "hold_failing_endpoints": t.get("ths_failing_endpoints"),
                     "timing_met": t.get("timing_met"),
                     "period_ns": (sp[0]["requirement_ns"] if sp else None)}
    out["setup_path"] = sp[0] if sp else None
    out["setup_features"] = timing.features(sp[0]) if sp else {}
    out["hold_path"] = hp[0] if hp else None
    u = dict(g.get("utilization") or {})
    out["utilization"] = u
    hier_txt = _read(d, "utilization_hier.rpt")
    rows = utilization.parse_hier(hier_txt) if hier_txt else []
    if hier_txt:
        files.append("utilization_hier.rpt")
    out["util_top"] = {k: [{"path": r["path"], "module": r["module"], k: r.get(k)} for r in utilization.top(rows, k, 4)]
                       for k in ("lut", "ff", "bram_tile", "dsp")} if rows else {}
    out["hier_modules"] = {r["path"]: r["module"] for r in utilization.paths(rows) if not r["own"]} if rows else {}
    ptxt = _read(d, "power.rpt")
    if ptxt:
        files.append("power.rpt")
    p = g.get("power") or {}
    env = g.get("power_environment") or {}
    out["power"] = {"total_w": p.get("total_w"), "dynamic_w": p.get("dynamic_w"), "static_w": p.get("static_w"),
                    "confidence": p.get("confidence"), "junction_c": env.get("junction_c"),
                    "components": pw.parse_components(ptxt) if ptxt else {},
                    "hierarchy": pw.parse_hierarchy(ptxt)[:12] if ptxt else []}
    log = _read(d, "vivado.log")
    out["synth"] = synth.scan(log) if log else {"latches": [], "ram_in_registers": [], "clean": True, "unread": True}
    if log:
        files.append("vivado.log")
    out["files"] = files
    return out


def digest_text(dg: dict[str, Any], goal: str | None = None) -> str:
    """The digest as prompt text. ``goal`` (G2/G3/G4) puts that goal's section first and drops the others' detail."""
    t = dg.get("timing") or {}
    u = dg.get("utilization") or {}
    p = dg.get("power") or {}
    parts = []
    tim = [f"TIMING: WNS {t.get('wns_ns')} ns, TNS {t.get('tns_ns')} ns over {t.get('failing_endpoints')} failing endpoints, "
           f"WHS {t.get('whs_ns')} ns, clock period {t.get('period_ns')} ns."]
    if dg.get("setup_path"):
        tim.append(timing.path_text(dg["setup_path"]))
    if dg.get("hold_path") and not dg["hold_path"]["met"]:
        tim.append(timing.path_text(dg["hold_path"]))
    area = [f"AREA: LUT {u.get('lut')}/{u.get('lut_available')}, FF {u.get('ff')}/{u.get('ff_available')}, "
            f"BRAM tiles {u.get('bram_tile')}/{u.get('bram_tile_available')}, DSP {u.get('dsp')}/{u.get('dsp_available')}, "
            f"IO {u.get('iob')}/{u.get('iob_available')}, CARRY4 {u.get('carry4')}."]
    for k, rows in (dg.get("util_top") or {}).items():
        if rows and any(r.get(k) for r in rows) and (goal in (None, "G3") or k in ("lut", "ff")):
            area.append(f"  largest {k} users: " + ", ".join(f"{r['path'] or '(top)'} ({r['module']}) {r.get(k)}" for r in rows if r.get(k)))
    s = dg.get("synth") or {}
    if s.get("latches") or s.get("ram_in_registers"):
        area.append(f"  synthesis: latches {s.get('latches')}, RAM implemented in registers {s.get('ram_in_registers')}")
    powr = [f"POWER: total {p.get('total_w')} W (dynamic {p.get('dynamic_w')}, static {p.get('static_w')}), junction "
            f"{p.get('junction_c')} C, confidence {p.get('confidence')}."]
    if p.get("components") and goal in (None, "G4"):
        powr.append("  by type: " + ", ".join(f"{k} {v}" for k, v in p["components"].items() if k not in ("Total",)))
    if p.get("hierarchy") and goal in (None, "G4"):
        powr.append("  by hierarchy: " + ", ".join(f"{'  ' * r['depth']}{r['name']} {r['power_w']}" for r in p["hierarchy"][:8]))
    order = {"G2": (tim, area, powr), "G3": (area, tim, powr), "G4": (powr, tim, area)}.get(goal or "", (tim, area, powr))
    for sec in order:
        parts += sec
    return "\n".join(parts)
