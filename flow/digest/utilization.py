"""``report_utilization -hierarchical`` by instance.

``parse_hier(text)`` returns one row per table line: ``{instance, module, depth, own, lut, logic_lut, lutram, srl, ff,
ramb36, ramb18, bram_tile, dsp}``. ``own`` is true for the ``(name)`` rows Vivado prints for a cell's own logic (not its
children). ``bram_tile`` = RAMB36 + RAMB18 / 2. ``top(rows, key, n)`` gives the largest leaf-own users of a resource.
"""

from __future__ import annotations

import re
from typing import Any

_COLS = {"Total LUTs": "lut", "Logic LUTs": "logic_lut", "LUTRAMs": "lutram", "SRLs": "srl", "FFs": "ff",
         "RAMB36": "ramb36", "RAMB18": "ramb18", "DSP Blocks": "dsp", "DSP48 Blocks": "dsp"}


def parse_hier(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    head_i = next((i for i, l in enumerate(lines) if l.startswith("|") and "Instance" in l and "Module" in l), None)
    if head_i is None:
        return []
    heads = [h.strip() for h in lines[head_i].strip().strip("|").split("|")]
    rows = []
    for l in lines[head_i + 2:]:
        if not l.startswith("|"):
            if rows:
                break
            continue
        raw = l[1:].rstrip().rstrip("|").split("|")
        if len(raw) != len(heads):
            continue
        name_cell = raw[0]
        depth = (len(name_cell) - len(name_cell.lstrip(" ")) - 1) // 2
        inst = name_cell.strip()
        r: dict[str, Any] = {"instance": inst.strip("()"), "own": inst.startswith("("), "depth": max(depth, 0),
                             "module": raw[1].strip()}
        for h, v in zip(heads[2:], raw[2:]):
            key = _COLS.get(h)
            if key:
                try:
                    r[key] = float(v.strip()) if "." in v else int(v.strip())
                except ValueError:
                    r[key] = 0
        r["bram_tile"] = r.get("ramb36", 0) + r.get("ramb18", 0) / 2
        rows.append(r)
    return rows


def paths(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows with their full hierarchical path (``u_regs/u_core``), the top cell as ``""``."""
    stack: list[str] = []
    out = []
    for r in rows:
        d = r["depth"]
        if r["own"]:
            path = "/".join(stack[1:d])
        else:
            stack = stack[:d] + [r["instance"]]
            path = "/".join(stack[1:])
        out.append({**r, "path": path})
    return out


def top(rows: list[dict[str, Any]], key: str = "lut", n: int = 5) -> list[dict[str, Any]]:
    """The ``n`` largest users of ``key`` by their own logic (the ``(name)`` rows, and leaves with no own row)."""
    pr = paths(rows)
    has_own = {r["path"] for r in pr if r["own"]}
    leaves = [r for r in pr if r["own"] or (r["path"] not in has_own and r["depth"] > 0
                                           and not any(o["path"].startswith(r["path"] + "/") for o in pr if o is not r))]
    return sorted(leaves, key=lambda r: -(r.get(key) or 0))[:n]
