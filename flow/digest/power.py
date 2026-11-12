"""``report_power``: on-chip components by type and power by hierarchy (brief 62A).

``parse_components(text)`` -> ``{Clocks: 0.011, "Slice Logic": 0.010, Signals: ..., "Block RAM": ..., "I/O": ...,
"Static Power": ..., Total: ...}`` (W; ``<0.001`` reads as 0.0005, as flow/gates.py does).
``parse_hierarchy(text)`` -> ``[{name, depth, power_w}]`` from section "By Hierarchy".
"""

from __future__ import annotations

import re
from typing import Any


def _w(v: str) -> float:
    v = v.strip()
    if v.startswith("<"):
        return float(v[1:]) / 2
    return float(v)


def parse_components(text: str) -> dict[str, float]:
    m = re.search(r"^\|\s*On-Chip\s*\|\s*Power \(W\).*?\n(.*?)\n\+-+\+-+[^\n]*\n\s*\n", text, re.M | re.S)
    out: dict[str, float] = {}
    if not m:
        return out
    for l in m.group(1).splitlines():
        cols = [c.strip() for c in l.strip().strip("|").split("|")]
        if len(cols) >= 2 and cols[0] and not cols[0].startswith("-") and not cols[0].startswith("+"):
            try:
                out[cols[0]] = _w(cols[1])
            except ValueError:
                continue
    return out


def parse_hierarchy(text: str) -> list[dict[str, Any]]:
    m = re.search(r"By Hierarchy\s*\n-+\s*\n\s*\n\+[-+]+\+\s*\n\|\s*Name\s*\|\s*Power \(W\)\s*\|\s*\n\+[-+]+\+\s*\n(.*?)\n\+[-+]+\+",
                  text, re.S)
    if not m:
        return []
    rows = []
    for l in m.group(1).splitlines():
        if not l.startswith("|"):
            continue
        name, pw = l[1:].rstrip().rstrip("|").split("|")[:2]
        depth = (len(name) - len(name.lstrip(" ")) - 1) // 2
        try:
            rows.append({"name": name.strip(), "depth": max(depth, 0), "power_w": _w(pw)})
        except ValueError:
            continue
    return rows
