#!/usr/bin/env python3
"""An early logic-depth estimate from Yosys, without Vivado (brief 231 item 8; the technique is Edwards 2026, appendix D).

``synth_xilinx`` maps the design to LUTs, carries and wide muxes in seconds; this reads the netlist (``write_json``) and
counts the longest combinational chain of those cells between registers, ports and hard blocks. Advisory only: Vivado's
``report_design_analysis`` and ``report_timing`` stay the sign-off (results/231_yosys_depth measures how well the estimate
ranks designs against Vivado's synthesis-stage logic levels, and where it does not).

Weights: LUTn and MUXF7/8/9 count 1 each; CARRY8 counts 1 and CARRY4 counts 0.5, since Vivado reads a CARRY4 of a Yosys netlist
as half of a CARRY8 (results/b142: "Unisim Transformation Summary"). Registers, DSPs, block RAMs and ports start and end a path.

    python3 -m flow.yosys_depth --top T [--family xcup] [-G NAME=VAL ...] SRC.sv [SRC.sv ...]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

WEIGHT = {"CARRY4": 0.5, "CARRY8": 1.0, "MUXF7": 1.0, "MUXF8": 1.0, "MUXF9": 1.0}
OUT_PINS = {"CARRY4": ("CO", "O"), "CARRY8": ("CO", "O"), "MUXF7": ("O",), "MUXF8": ("O",), "MUXF9": ("O",)}


def comb_cell(ctype: str) -> bool:
    return ctype in WEIGHT or (ctype.startswith("LUT") and ctype[3:].isdigit())


def cell_weight(ctype: str) -> float:
    return WEIGHT.get(ctype, 1.0)


def depth_from_json(netlist: dict[str, Any], top: str | None = None) -> dict[str, Any]:
    """Longest chain of combinational cells in the (flattened) top module of a Yosys ``write_json`` netlist:
    ``{"depth": float, "levels": int, "path": [cell types], "cells": n}`` (``levels`` is the depth rounded up)."""
    mods = netlist["modules"]
    mod = mods[top] if top and top in mods else next((m for m in mods.values() if (m.get("attributes") or {}).get("top")),
                                                      next(iter(mods.values())))
    driver: dict[int, tuple[str, str]] = {}                  # bit -> (cell, type) of the combinational cell that drives it
    for name, c in mod["cells"].items():
        if not comb_cell(c["type"]):
            continue
        outs = OUT_PINS.get(c["type"], ("O",))
        for pin in outs:
            for b in c["connections"].get(pin, []):
                if isinstance(b, int):
                    driver[b] = (name, c["type"])
    memo: dict[str, tuple[float, tuple[str, ...]]] = {}

    def arrival(cell: str) -> tuple[float, tuple[str, ...]]:
        if cell in memo:
            return memo[cell]
        memo[cell] = (0.0, ())                               # a combinational loop counts once
        c = mod["cells"][cell]
        outs = OUT_PINS.get(c["type"], ("O",))
        best: tuple[float, tuple[str, ...]] = (0.0, ())
        for pin, bits in c["connections"].items():
            if pin in outs:
                continue
            for b in bits:
                d = driver.get(b) if isinstance(b, int) else None
                if d and d[0] != cell:
                    a = arrival(d[0])
                    if a[0] > best[0]:
                        best = a
        res = (best[0] + cell_weight(c["type"]), best[1] + (c["type"],))
        memo[cell] = res
        return res

    best = (0.0, ())
    for cell, _t in {v for v in driver.values()}:
        a = arrival(cell)
        if a[0] > best[0]:
            best = a
    depth = best[0]
    return {"depth": depth, "levels": int(depth + 0.999), "path": list(best[1]),
            "cells": sum(1 for c in mod["cells"].values() if comb_cell(c["type"]))}


def find_yosys() -> str | None:
    from flow.checks.elab import find_tool
    t = find_tool()
    return t[0] if t else None


def run_yosys(sources: list[Path], top: str, family: str = "xcup", generics: dict[str, str] | None = None,
              flatten: bool = True, timeout: int = 900) -> dict[str, Any]:
    """Synthesise with ``synth_xilinx`` and return ``depth_from_json`` of the result (SystemVerilog through the slang plugin)."""
    from flow.checks.elab import find_tool
    t = find_tool()
    if not t:
        raise RuntimeError("Yosys (OSS CAD Suite) not found")
    exe, env = t
    gen = " ".join(f"-G {k}={v}" for k, v in (generics or {}).items())
    with tempfile.TemporaryDirectory() as td:
        js = Path(td) / "n.json"
        cmds = (f"plugin -i slang; read_slang --top {top} {gen} " + " ".join(map(str, sources)) +
                f"; synth_xilinx -family {family} -top {top} -noiopad -noclkbuf {'-flatten' if flatten else ''}; write_json {js}")
        r = subprocess.run([exe, "-q", "-p", cmds], capture_output=True, text=True, env=env, timeout=timeout)
        if r.returncode != 0 or not js.is_file():
            raise RuntimeError((r.stderr or r.stdout)[-400:])
        return depth_from_json(json.loads(js.read_text()), top)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--top", required=True)
    ap.add_argument("--family", default="xcup", choices=("xc7", "xcu", "xcup"))
    ap.add_argument("-G", action="append", default=[], metavar="NAME=VAL")
    ap.add_argument("sources", nargs="+", type=Path)
    a = ap.parse_args(argv)
    res = run_yosys(a.sources, a.top, a.family, dict(g.split("=", 1) for g in a.G))
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())
