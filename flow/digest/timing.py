"""The critical path of a ``report_timing`` (``timing_worst_setup.rpt`` / ``timing_worst_hold.rpt``), parsed (brief 62A).

``parse_paths(text)`` returns one record per path in the report, worst first::

    {slack_ns, met, kind (setup|hold), source, destination, source_clock, dest_clock, path_group, requirement_ns,
     data_path_ns, logic_ns, route_ns, route_pct, logic_levels, levels_by_type {CARRY4: 7, ...}, skew_ns,
     uncertainty_ns, cells: [{type, name, incr_ns}], nets: [{fanout, incr_ns, name}],
     source_reg {instance, signal, bit}, dest_reg {...}}

``features(path)`` names what the path is made of, for the playbook: ``carry_chain`` (CARRY4 cells), ``lut_levels``,
``max_fanout`` (and its net), ``route_dominated`` (route share of the data path >= 60 %), ``dsp_on_path``,
``bram_on_path``, ``lut_arith`` (a carry chain of 4 or more with no DSP on the path: an adder or a multiplier built in
LUTs), ``same_instance`` (both ends in one RTL instance: the fix is local to one module).
"""

from __future__ import annotations

import re
from typing import Any

_HDR = re.compile(r"^Slack \((MET|VIOLATED)\)\s*:\s*(-?[0-9.]+)ns", re.M)
_CELL = re.compile(r"^\s+(?:\S+\s+)?([A-Z][A-Z0-9_]+) \((Prop|Setup|Hold)_[^)]*\)\s*(?:\n\s+)?(-?[0-9.]+)\s+(-?[0-9.]+)\s+[rf]?\s*(\S+)",
                   re.M)
_NET = re.compile(r"^\s+net \(fo=(\d+)(?:, (?:routed|estimated|unplaced))?\)\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s+(\S+)", re.M)
_REG = re.compile(r"^(?P<inst>.*?)/?(?P<sig>[A-Za-z_][\w$]*?)(?:_reg)(?:\[(?P<bit>\d+)\])?(?:\[\d+\])*(?:_\w+)?/(?:C|D|Q|CE|R|S|CLR|PRE)$")


def _num(blk: str, key: str) -> float | None:
    m = re.search(rf"^\s*{key}:\s*(-?[0-9.]+)ns", blk, re.M)
    return float(m.group(1)) if m else None


def _word(blk: str, key: str) -> str | None:
    m = re.search(rf"^\s*{key}:\s*(\S+)", blk, re.M)
    return m.group(1) if m else None


def reg_name(pin: str | None) -> dict[str, Any] | None:
    """``u_regs/u_core/k_reg[2]/C`` -> ``{instance: u_regs/u_core, signal: k, bit: 2}``; a pin that is not a register's
    (a port, a RAM, a DSP) gives ``{instance, signal: None, cell}``."""
    if not pin:
        return None
    m = _REG.match(pin)
    if m:
        return {"instance": m.group("inst"), "signal": m.group("sig"),
                "bit": int(m.group("bit")) if m.group("bit") is not None else None}
    cell = pin.rsplit("/", 1)[0] if "/" in pin else pin
    return {"instance": cell.rsplit("/", 1)[0] if "/" in cell else "", "signal": None, "cell": cell}


def _path_body(blk: str) -> str:
    """The data path section: from the source register's clock pin row to the destination pin row (the second dashed
    rule to the third); empty if the layout is not the usual one."""
    rules = [m.start() for m in re.finditer(r"^\s+-{20,}", blk, re.M)]
    if len(rules) >= 3:
        return blk[rules[1]:rules[2]]
    return blk


def parse_paths(text: str) -> list[dict[str, Any]]:
    heads = list(_HDR.finditer(text))
    out = []
    for i, h in enumerate(heads):
        blk = text[h.start():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        dp = re.search(r"Data Path Delay:\s*(-?[0-9.]+)ns\s*\(logic (-?[0-9.]+)ns \(([0-9.]+)%\)\s*route (-?[0-9.]+)ns \(([0-9.]+)%\)\)",
                       blk)
        ll = re.search(r"Logic Levels:\s*(\d+)\s*(?:\(([^)]*)\))?", blk)
        by_type = {}
        if ll and ll.group(2):
            for part in ll.group(2).split():
                if "=" in part:
                    k, v = part.split("=", 1)
                    by_type[k] = int(v)
        clk = re.findall(r"clocked by (\S+)", blk)
        ptype = _word(blk, "Path Type") or ""
        body = _path_body(blk)
        cells = [{"type": m.group(1), "name": m.group(5), "incr_ns": float(m.group(3))}
                 for m in _CELL.finditer(body) if m.group(2) == "Prop"]
        nets = [{"fanout": int(m.group(1)), "incr_ns": float(m.group(2)), "name": m.group(4)} for m in _NET.finditer(body)]
        src, dst = _word(blk, "Source"), _word(blk, "Destination")
        out.append({
            "slack_ns": float(h.group(2)), "met": h.group(1) == "MET",
            "kind": "hold" if ptype.startswith("Hold") else "setup",
            "source": src, "destination": dst,
            "source_clock": clk[0] if clk else None, "dest_clock": clk[1] if len(clk) > 1 else None,
            "path_group": _word(blk, "Path Group"), "requirement_ns": _num(blk, "Requirement"),
            "data_path_ns": float(dp.group(1)) if dp else None, "logic_ns": float(dp.group(2)) if dp else None,
            "route_ns": float(dp.group(4)) if dp else None, "route_pct": float(dp.group(5)) if dp else None,
            "logic_levels": int(ll.group(1)) if ll else None, "levels_by_type": by_type,
            "skew_ns": _num(blk, "Clock Path Skew"), "uncertainty_ns": _num(blk, "Clock Uncertainty"),
            "cells": cells, "nets": nets, "source_reg": reg_name(src), "dest_reg": reg_name(dst),
        })
    return sorted(out, key=lambda p: p["slack_ns"])


HIGH_FANOUT = 64          # a net driving this many loads on a failing path is worth replicating or registering


def features(p: dict[str, Any]) -> dict[str, Any]:
    t = p.get("levels_by_type") or {}
    carry = t.get("CARRY4", 0) + t.get("CARRY8", 0)
    luts = sum(v for k, v in t.items() if k.startswith("LUT"))
    # the first net leaves the source register: count it too (k_reg in c13 drives 103 loads)
    fo = max(p.get("nets") or [{"fanout": 0, "name": None}], key=lambda n: n["fanout"])
    types = {c["type"] for c in p.get("cells") or []} | set(t)
    dsp = any(x.startswith("DSP48") for x in types)
    bram = any(x.startswith("RAMB") for x in types)
    s, d = p.get("source_reg") or {}, p.get("dest_reg") or {}
    return {
        "carry_chain": carry, "lut_levels": luts, "logic_levels": p.get("logic_levels"),
        "max_fanout": fo["fanout"], "max_fanout_net": fo["name"], "high_fanout": fo["fanout"] >= HIGH_FANOUT,
        "route_pct": p.get("route_pct"), "route_dominated": (p.get("route_pct") or 0) >= 60.0,
        "dsp_on_path": dsp, "bram_on_path": bram, "lut_arith": carry >= 4 and not dsp,
        "same_instance": bool(s.get("instance") is not None and s.get("instance") == d.get("instance")),
        "cross_clock": p.get("source_clock") != p.get("dest_clock"),
    }


def path_text(p: dict[str, Any], limit_cells: int = 16) -> str:
    """One compact paragraph for the repair prompt."""
    f = features(p)
    s, d = p.get("source_reg") or {}, p.get("dest_reg") or {}
    lv = " ".join(f"{k}={v}" for k, v in sorted((p.get("levels_by_type") or {}).items()))
    chain = " -> ".join(c["type"] for c in (p.get("cells") or [])[:limit_cells])
    return (f"worst {p['kind']} path: slack {p['slack_ns']:+.3f} ns, requirement {p.get('requirement_ns')} ns; "
            f"from {p.get('source')} (RTL signal {s.get('signal')!s} in instance {s.get('instance')!s}) "
            f"to {p.get('destination')} (RTL signal {d.get('signal')!s} in instance {d.get('instance')!s}); "
            f"data path {p.get('data_path_ns')} ns = logic {p.get('logic_ns')} + route {p.get('route_ns')} ({p.get('route_pct')} % route); "
            f"{p.get('logic_levels')} logic levels ({lv}); cells: {chain}; "
            f"largest fanout on the path {f['max_fanout']} ({f['max_fanout_net']}); DSP on path: {f['dsp_on_path']}.")
