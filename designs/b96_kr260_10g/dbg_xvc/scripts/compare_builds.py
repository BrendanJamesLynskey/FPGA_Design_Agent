#!/usr/bin/env python3
"""Brief 131: compare the parent build (eyescan) with dbg_xvc from two dumps of dump_netlist_timing.tcl and the two builds' gates.json.

    compare_builds.py <parent dump dir> <dbg dump dir> <parent gates.json> <dbg gates.json> <out summary.json>

Writes the summary the testplan item V-XVC-TRADING-PATH reads: core cells removed and added (library cell per name), worst slack per clock and through the trading path in both builds,
and the utilisation difference. Measured numbers only; nothing here judges timing (the gates do)."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def cells(d: Path) -> dict[str, str]:
    return dict(ln.rstrip("\n").split("|", 1) for ln in (d / "cells.txt").read_text().splitlines() if "|" in ln)


def table(d: Path, name: str) -> dict[str, list[str]]:
    out = {}
    for ln in (d / name).read_text().splitlines():
        p = ln.split("|")
        out[p[0] + "|" + (p[1] if name == "paths.txt" else "")] = p[2:]
    return out


def lines(d: Path, name: str) -> list[str]:
    return (d / name).read_text().splitlines()


def main() -> None:
    pd, dd, pg, dg, out = (Path(a) for a in sys.argv[1:6])
    pc, dc = cells(pd), cells(dd)
    # LUT, carry and mux cells carry tool-made names (h_rdata[0]_i_10) that change from run to run, so they are compared by count per u_core child; every other cell
    # (flops, RAM, GT, clock buffers ...) has a name from the RTL and is compared by name and library cell
    def logic(r):
        return r.startswith(("LUT", "CARRY", "MUXF"))
    pn = {n: r for n, r in pc.items() if not logic(r)}
    dn = {n: r for n, r in dc.items() if not logic(r)}
    removed = sorted(set(pn) - set(dn))
    added = sorted(set(dn) - set(pn))
    changed_ref = sorted(n for n in set(pn) & set(dn) if pn[n] != dn[n])
    outside = list(added)          # the debug taps are wires: no cell may be added under u_core
    def per_child(c):
        out = {}
        for n, r in c.items():
            if logic(r):
                k = n.split("/")[1]
                k = k if k.startswith(("u_", "g_")) else "(core top level)"
                out[k] = out.get(k, 0) + 1
        return out
    lp, ld = per_child(pc), per_child(dc)
    logic_delta = {k: ld.get(k, 0) - lp.get(k, 0) for k in sorted(set(lp) | set(ld))}
    pj, dj = json.loads(pg.read_text()), json.loads(dg.read_text())
    pu = pj["utilization"]
    du = dj["utilization"]
    res = {
        "parent": "designs/b96_kr260_10g/eyescan", "debug": "designs/b96_kr260_10g/dbg_xvc",
        "core_cells_parent": len(pc), "core_cells_dbg": len(dc), "core_named_cells_parent": len(pn), "core_named_cells_dbg": len(dn),
        "core_logic_cells_per_child_parent": lp, "core_logic_cells_per_child_dbg": ld, "core_logic_cells_delta_per_child": logic_delta,
        "core_cells_removed": len(removed), "core_cells_added": len(added), "core_cells_added_outside_taps": len(outside), "core_cells_changed_library_cell": len(changed_ref),
        "removed_sample": removed[:20], "added_sample": added[:20], "changed_sample": changed_ref[:20],
        "per_clock_parent": lines(pd, "per_clock.txt"), "per_clock_dbg": lines(dd, "per_clock.txt"),
        "trading_paths_parent": lines(pd, "paths.txt"), "trading_paths_dbg": lines(dd, "paths.txt"),
        "core_children_cells_parent": lines(pd, "hier_util.txt"), "core_children_cells_dbg": lines(dd, "hier_util.txt"),
        "tap_nets_dbg": lines(dd, "tap_fanout.txt"), "tap_nets_parent": lines(pd, "tap_fanout.txt"),
        "utilization_parent": pu, "utilization_dbg": du,
        "utilization_delta": {k: round(du[k] - pu[k], 2) for k in pu if isinstance(pu[k], (int, float)) and not k.endswith("available")},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in ("core_cells_parent", "core_cells_dbg", "core_named_cells_parent", "core_named_cells_dbg", "core_logic_cells_delta_per_child", "core_cells_removed", "core_cells_added", "core_cells_added_outside_taps", "utilization_delta")}, indent=1))


if __name__ == "__main__":
    main()
