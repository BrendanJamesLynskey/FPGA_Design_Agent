#!/usr/bin/env python3
"""Assurance checks and cost measurement (brief 194): the netlist-level checks of the `thorough` profile and the area/Fmax cost of the
reliability structures. See docs/assurance.md.

    python3 -m flow.assurance cost --variants u ecc_prim ...   Vivado 2026.1 out-of-context synthesis and routing of the development design
    python3 -m flow.assurance netsim ...                       the functional bench on the post-synthesis netlist (xsim)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "designs" / "b194_assurance"
sys.path.insert(0, str(ROOT))
from flow.ipchar import tcl_list, vivado  # noqa: E402

PART = "xc7a100tcsg324-1"
sys.path.insert(0, str(DESIGN / "tests"))
from run_faults import VARIANTS  # noqa: E402


def sources() -> list[str]:
    return [str(DESIGN / "rtl" / f) for f in ("a194_secded.sv", "a194_fifo.sv", "a194_ctrl.sv", "a194_core.sv")]


def generics(v: tuple) -> list[str]:
    return [f"{k}={x}" for k, x in zip(("ECC", "PAR", "SAFE", "TMR", "WD"), v)]


def cost(names: list[str], work: Path, period: float, impl: bool, mem: str = "4G") -> dict:
    work.mkdir(parents=True, exist_ok=True)
    lines = [f"set aj(part) {PART}", "set aj(top) a194_core", f"set aj(period) {period}", "set aj(jobs) {}"]
    for n in names:
        lines.append("lappend aj(jobs) " + tcl_list([n, str(work / n), generics(VARIANTS[n]), sources(), int(impl)]))
    (work / "jobs.tcl").write_text("\n".join(lines) + "\n")
    cmd = ["systemd-run", "--user", "--scope", "--quiet", f"-p", f"MemoryMax={mem}", "nice", "-n", "15", vivado(), "-mode", "batch", "-nojournal",
           "-log", str(work / "vivado.log"), "-source", str(ROOT / "flow" / "assurance_ooc.tcl"), "-tclargs", str(work / "jobs.tcl")]
    t0 = time.time()
    subprocess.run(cmd, cwd=work)
    out = {"wall_s": round(time.time() - t0, 1)}
    for n in names:
        d = work / n / "done.txt"
        out[n] = dict(l.split(" ", 1) for l in d.read_text().splitlines()) if d.exists() else {"ok": "0", "error": "no done.txt"}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cost")
    c.add_argument("--variants", nargs="+", default=list(VARIANTS))
    c.add_argument("--work", type=Path, default=ROOT / "build" / "b194" / "cost")
    c.add_argument("--period", type=float, default=5.0)
    c.add_argument("--synth-only", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "cost":
        r = cost(a.variants, a.work, a.period, not a.synth_only)
        print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
