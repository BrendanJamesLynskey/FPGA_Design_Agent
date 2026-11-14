#!/usr/bin/env python3
"""A real formal counterexample, recorded for replay (brief 81).

    python3 axi_tx/formal/counterexample.py [--mutant b_early_aw_only] [--depth 12] [--out results/81_verification/counterexample.json]

Runs the AXI4-Lite checker's seed proof for the mutated rule (bounded, SymbiYosys, z3: whenever the rule is broken the checker must
flag it) on one checker mutant from run_formal.py's semantic list,
takes the counterexample the solver finds, and writes the signals of the cycles up to the failure as JSON. The default
mutant checks for an early write response against the address channel alone, so the proof fails at a trace where a write
response arrives before the write data and the mutated checker stays silent. The page replays this file; nothing in it is typed by hand.
Needs sby, yosys and z3 on PATH (set FDA_OSS_CAD to the OSS CAD Suite folder).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import run_formal as rf  # noqa: E402

PERIOD = 10      # SymbiYosys writes a trace with a time step of 5 per clock phase: one clock cycle is 10
SIGNALS = ["aresetn", "awvalid", "awready", "wvalid", "wready", "bvalid", "bready", "viol"]


def parse_vcd(path: Path, names: list[str]) -> dict[str, list[int]]:
    """Value of each named top-level signal at every timestep of the trace (a clock edge per step; 'x' becomes 0)."""
    ids: dict[str, str] = {}
    scope = []
    vals: dict[str, int] = {n: 0 for n in names}
    steps: list[dict[str, int]] = []
    in_defs = True
    cur_t = None
    for line in path.read_text().splitlines():
        line = line.strip()
        if in_defs:
            if line.startswith("$scope"):
                scope.append(line.split()[2])
            elif line.startswith("$upscope"):
                scope.pop()
            elif line.startswith("$var"):
                p = line.split()
                if len(scope) == 1 and p[4] in names and p[4] not in ids.values():
                    ids[p[3]] = p[4]
            elif line.startswith("$enddefinitions"):
                in_defs = False
            continue
        if line.startswith("#"):
            if cur_t is not None and cur_t % PERIOD == 0:
                steps.append(dict(vals))          # the state at the end of a clock-edge time step
            cur_t = int(line[1:])
        elif line and line[0] in "01xz" and line[1:] in ids:
            vals[ids[line[1:]]] = 1 if line[0] == "1" else 0
        elif line.startswith("b"):
            v, i = line[1:].split()
            if i in ids:
                vals[ids[i]] = int(v.replace("x", "0"), 2)
    if cur_t is not None and cur_t % PERIOD == 0:
        steps.append(dict(vals))
    return {n: [s[n] for s in steps] for n in names}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mutant", default="b_early_aw_only")
    ap.add_argument("--depth", type=int, default=12)
    ap.add_argument("--work", type=Path, default=ROOT / "build" / "81" / "cex")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "81_verification" / "counterexample.json")
    a = ap.parse_args(argv)
    cad = os.environ.get("FDA_OSS_CAD")
    if cad:
        os.environ["PATH"] = f"{cad}/bin:" + os.environ["PATH"]
    for exe in ("sby", "yosys", "z3"):
        if not shutil.which(exe):
            print(f"{exe} not found: set FDA_OSS_CAD", file=sys.stderr)
            return 2
    unit = rf.UNITS["axil"]
    text = (rf.RTL / unit["rtl"]).read_text()
    sem = [s for s in rf.SEMANTIC if s[0] == "axil" and s[1] == a.mutant]
    if not sem:
        print(f"no semantic mutant {a.mutant}", file=sys.stderr)
        return 2
    _, name, rule, old, new = sem[0]
    if old not in text:
        print("mutation text not found in the RTL", file=sys.stderr)
        return 2
    rf.OUT = a.work
    r = rf.run_job(f"cex_{name}", unit, text.replace(old, new, 1), f"-DSEED={rule}", "bmc", a.depth)
    if r["status"] != "FAIL":
        print(f"the proof did not fail on the mutant: {r}", file=sys.stderr)
        return 1
    run = a.work / f"cex_{name}" / "run"
    vcd = next(run.glob("engine_*/trace.vcd"))
    log = (a.work / f"cex_{name}" / "sby.log").read_text()
    failed_step = int(re.findall(r"Checking assertions in step (\d+)", log)[-1])
    sig = parse_vcd(vcd, SIGNALS)
    n = failed_step + 1
    out = {"mutant": name, "rule": rule, "rule_name": "B_EARLY", "mutation": {"old": old, "new": new}, "proof": f"seed{rule}",
           "depth": a.depth, "failing_step": failed_step, "solver": "z3 through SymbiYosys",
           "tool": subprocess.run(["yosys", "-V"], capture_output=True, text=True).stdout.strip(),
           "signals": {k: v[:n] for k, v in sig.items() if k != "viol"}, "cycles": n,
           "checker_flags": [(x >> rule) & 1 for x in sig["viol"][:n]]}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(f"counterexample at step {failed_step}: wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
