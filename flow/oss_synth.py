#!/usr/bin/env python3
"""Open-source synthesis of one block for a Xilinx part, delay-driven, written as EDIF for Vivado (brief 101).

Yosys (OSS CAD Suite, pinned 20261112, found as in flow/checks/elab.py) reads the sources with the slang plugin, runs
``synth_xilinx`` for the family, maps LUTs with ABC, and writes an EDIF (for ``read_edif`` in Vivado, out of context) and
a Verilog netlist of the same cells (for flow/eqy_gate.py). Nothing here estimates timing: Vivado's timing analysis of
the EDIF is the referee (flow/oss_compare/run.py).

The ABC scripts (``SCRIPTS``) are the whole choice, and each is recorded verbatim in the result:

* ``abc9``      ``synth_xilinx`` as shipped: ``abc9 -luts 2:2,3,6:5,10,20``, the timing-driven ABC9 flow, with the LUT, CARRY
                and MUX delays taken from the ``specify`` blocks of ``+/xilinx/cells_sim.v``; no delay target (ABC maps for the
                best delay it finds, then recovers area off the critical path).
* ``abc9_dff``  the same with ``-dff``: flip-flops pass through ABC9 as boxes, which lets ABC's sequential steps (register
                correspondence, retiming of the combinational cone it sees) act. It can move or merge registers, so a register
                correspondence by name no longer holds: use the induction strategy of flow/eqy_gate.py.
* ``abc_d``     the classic ``abc`` pass with a delay target (``-D <ps>``, default 1 ps: "as fast as possible"), LUT cost table
                ``2:2,3,6:5,10,20``; no timing boxes for CARRY or MUX, so it sees only LUT depth.

Run: ``python -m flow.oss_synth --top ooc_wrap --family xcup --script abc9 --out <dir> src1.sv src2.sv``.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from flow.checks.elab import find_tool

FAMILIES = {"xc7": "7-series", "xcu": "UltraScale", "xcup": "UltraScale+"}
#: part prefix -> synth_xilinx family
PART_FAMILY = {"xck26": "xcup", "xczu": "xcup", "xcku": "xcu", "xc7a": "xc7", "xc7z": "xc7", "xc7k": "xc7"}
LUTS = "2:2,3,6:5,10,20"
SCRIPTS = {
    "abc9": "synth_xilinx -flatten (abc9 -luts %s)" % LUTS,
    "abc9_dff": "synth_xilinx -flatten -dff (abc9 -luts %s -dff)" % LUTS,
    "abc_d": "synth_xilinx -run begin:map_luts; abc -luts %s -D <ps>; techmap lut_map/cells_map; synth_xilinx -run finalize:" % LUTS,
}


class OssError(RuntimeError):
    pass


def family_of_part(part: str) -> str:
    for k, v in PART_FAMILY.items():
        if part.lower().startswith(k):
            return v
    raise OssError(f"no synth_xilinx family known for part {part}")


def yosys_script(top: str, sources: list[str], family: str, script: str, edif: str, netlist: str, d_ps: int = 1,
                 slang_defines: list[str] | None = None) -> str:
    """The Yosys commands as one string (recorded in the result)."""
    if script not in SCRIPTS:
        raise OssError(f"unknown script {script!r}; one of {sorted(SCRIPTS)}")
    d = " ".join(f"-D {x}" for x in slang_defines or [])
    read = f"plugin -i slang; read_slang --top {top} {d} " + " ".join(sources)
    common = f"-family {family} -top {top} -noiopad -noclkbuf"
    if script == "abc9":
        syn = f"synth_xilinx {common} -flatten"
    elif script == "abc9_dff":
        syn = f"synth_xilinx {common} -flatten -dff"
    else:
        lut_w = 6
        syn = (f"synth_xilinx {common} -flatten -run begin:map_luts; opt_expr -mux_undef -noclkinv; "
               f"abc -luts {LUTS} -D {d_ps}; clean; techmap -map +/xilinx/lut_map.v -map +/xilinx/cells_map.v -D LUT_WIDTH={lut_w}; "
               f"xilinx_dffopt; opt_lut_ins -tech xilinx; synth_xilinx {common} -run finalize:")
    return (f"{read}; {syn}; tee -o {edif}.stat stat -tech xilinx; write_edif -pvector bra {edif}; "
            f"write_verilog -noattr {netlist}")


def synth(top: str, sources: list[str], family: str, script: str, out: Path, d_ps: int = 1) -> dict:
    """Synthesise; returns the record (also written to ``<out>/synth.json``). Raises OssError if the suite is absent or fails."""
    t = find_tool()
    if t is None:
        raise OssError("yosys (OSS CAD Suite 20261112) not found: set FDA_OSS_CAD or install it under ~/.local/opt/oss-cad-suite")
    yosys, env = t
    out.mkdir(parents=True, exist_ok=True)
    edif, net, log = out / "netlist.edif", out / "netlist.v", out / "yosys.log"
    cmds = yosys_script(top, [str(Path(s).resolve()) for s in sources], family, script, str(edif), str(net), d_ps)
    t0 = time.time()
    r = subprocess.run([yosys, "-q", "-l", str(log), "-p", cmds], capture_output=True, text=True, env=env, timeout=1800)
    secs = time.time() - t0
    if r.returncode != 0 or not edif.exists():
        raise OssError(f"yosys failed ({r.returncode}): {(r.stderr or r.stdout)[-600:]}")
    stat = (Path(str(edif) + ".stat")).read_text()
    cells = {m.group(2): int(m.group(1)) for m in re.finditer(r"^\s+(\d+)\s+(\w+)\s*$", stat, re.M)}
    ver = subprocess.run([yosys, "-V"], capture_output=True, text=True, env=env).stdout.strip()
    rec = {"top": top, "family": family, "script": script, "script_text": SCRIPTS[script], "d_ps": d_ps if script == "abc_d" else None,
           "yosys": ver, "yosys_commands": cmds, "seconds": round(secs, 1), "cells": cells,
           "lut": sum(n for c, n in cells.items() if re.fullmatch(r"LUT[1-6]", c)),
           "ff": sum(n for c, n in cells.items() if re.fullmatch(r"FD\w+", c)),
           "carry": sum(n for c, n in cells.items() if c.startswith("CARRY")),
           "edif": str(edif), "netlist": str(net)}
    (out / "synth.json").write_text(json.dumps(rec, indent=1))
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--top", required=True)
    ap.add_argument("--family", choices=sorted(FAMILIES))
    ap.add_argument("--part", help="alternative to --family")
    ap.add_argument("--script", default="abc9", choices=sorted(SCRIPTS))
    ap.add_argument("--d-ps", type=int, default=1, help="delay target for --script abc_d")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("sources", nargs="+")
    a = ap.parse_args(argv)
    fam = a.family or family_of_part(a.part or "")
    try:
        rec = synth(a.top, a.sources, fam, a.script, a.out, a.d_ps)
    except OssError as e:
        print(f"oss_synth: {e}", file=sys.stderr)
        return 2
    print(json.dumps({k: rec[k] for k in ("script", "family", "lut", "ff", "carry", "seconds", "edif")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
