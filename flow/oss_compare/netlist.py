#!/usr/bin/env python3
"""Vivado post-synthesis funcsim netlists of every block and Vivado synthesis arm (brief 101, part 2b), for flow/eqy_gate.py.

    python3 -m flow.oss_compare.netlist --part xck26-sfvc784-2LV-c       # one Vivado session; takes a heavy slot outside
Writes build/b101/netlists/<part>/<block>__<arm>/{synth_funcsim.v,netlist.json}; then
``python3 -m flow.oss_compare.eqy_run --vivado build/b101/netlists/<part>/*``.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow.ipchar import tcl_list, vivado  # noqa: E402
from flow.oss_compare import run as P  # noqa: E402

TCL = Path(__file__).with_name("netlist.tcl")
VIV_ARMS = [a for a, k in P.ARMS.items() if k != "edif"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--part", required=True, choices=sorted(P.PARTS))
    ap.add_argument("--blocks", nargs="+", default=list(P.BLOCKS))
    ap.add_argument("--arms", nargs="+", default=VIV_ARMS, choices=VIV_ARMS)
    a = ap.parse_args(argv)
    root = ROOT / "build" / "b101" / "netlists" / P.PARTS[a.part]
    root.mkdir(parents=True, exist_ok=True)
    lines = [f"set nl(part) {a.part}", "set nl(jobs) {}"]
    dirs = []
    for b in a.blocks:
        for arm in a.arms:
            wd = root / f"{b}__{arm}"
            wd.mkdir(parents=True, exist_ok=True)
            (wd / "error.txt").unlink(missing_ok=True)
            lines.append("lappend nl(jobs) " + tcl_list([f"{b}__{arm}", P.TOP, str(wd), P.ARMS[arm], [str(s) for s in P.BLOCKS[b]]]))
            dirs.append((b, arm, wd))
    (root / "jobs.tcl").write_text("\n".join(lines) + "\n")
    cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit=b101-netlist-{P.PARTS[a.part]}", "-p", "MemoryMax=6G", "nice", "-n", "15",
           vivado(), "-mode", "batch", "-nojournal", "-log", str(root / "vivado.log"), "-source", str(TCL), "-tclargs", str(root / "jobs.tcl")]
    subprocess.run(cmd, cwd=root)
    log = (root / "vivado.log").read_text()
    m = re.search(r"Vivado v(\S+) \(64-bit\)", log)
    for b, arm, wd in dirs:
        if (wd / "synth_funcsim.v").exists():
            strategy = "auto"
            (wd / "netlist.json").write_text(json.dumps({"block": b, "label": arm, "part": a.part, "synth": P.ARMS[arm], "strategy": strategy,
                                                         "tool": f"Vivado {m.group(1) if m else 'unknown'}"}, indent=1))
        else:
            print(f"netlist: {b} {arm}: no netlist ({(wd / 'error.txt').read_text()[:200] if (wd / 'error.txt').exists() else 'not run'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
