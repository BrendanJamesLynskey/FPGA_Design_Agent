"""Does the viewer's graph match the synthesised design? (brief 65A)

Expected: every block of the graph at its RTL instance path (``u_tone/u_dds``) with the module the graph names, and, in
a generated wrapper, the library block (``u_ip``) and the register bank or window adapter. Found: the hierarchical
cells of the routed netlist (``annotate.tcl``), each with its original module name (Vivado's ``ORIG_REF_NAME``, so a
parameterised copy still matches).

It fails on a block of the graph missing from the netlist (optimised away, or renamed), on a module that differs, and
on a cell of the netlist, directly inside the top, a hierarchy or a wrapper, that the graph does not show. Cells inside
a library block (the shell's UART, for example) are that block's own business and are not compared.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

IGNORE = re.compile(r"^(dbg_hub|u_ila_\d+)")


def _mod(m: str) -> str:
    return re.sub(r"__parameterized\d+$", "", m or "")


def expected(g: dict) -> dict:
    """RTL path -> module, and the set of paths whose direct children must all be in the graph."""
    exp, open_paths = {}, {""}
    for lv in g["levels"].values():
        for b in lv["blocks"]:
            exp[b["rtl_path"]] = b["module"]
            if b["kind"] == "hierarchy":
                open_paths.add(b["rtl_path"])
            if b.get("wrapper"):
                open_paths.add(b["rtl_path"])
                inner = b["wrapper"]["inner"]
                exp[inner[0]] = b["component_top"] if b.get("component_top") else b["component"]
                exp[inner[1]] = "bd_axil_win" if b["wrapper"]["kind"] == "window" else "bd_axil_regs"
    return {"modules": exp, "open": open_paths}


def check(g: dict, hier: list[dict]) -> dict:
    E = expected(g)
    found = {h["path"]: _mod(h["module"]) for h in hier if not IGNORE.match(h["path"])}
    mism = []
    matched = 0
    for p, m in sorted(E["modules"].items()):
        if p not in found:
            mism.append(f"{p} ({m}) is in the diagram but not in the synthesised hierarchy")
        elif found[p] != m:
            mism.append(f"{p}: the diagram says {m}, the netlist has {found[p]}")
        else:
            matched += 1
    for p in sorted(found):
        parent = p.rsplit("/", 1)[0] if "/" in p else ""
        if parent in E["open"] and p not in E["modules"]:
            mism.append(f"{p} ({found[p]}) is in the synthesised hierarchy but not in the diagram")
    return {"pass": not mism, "matched": matched, "expected": len(E["modules"]), "mismatches": mism}


def check_files(graph: Path, hier: Path) -> dict:
    g = json.loads(Path(graph).read_text())
    h = json.loads(Path(hier).read_text())
    return check(g, h["hier"] if isinstance(h, dict) else h)
