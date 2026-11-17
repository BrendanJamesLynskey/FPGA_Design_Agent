#!/usr/bin/env python3
"""Equivalence checking of generated register blocks with eqy (brief 81).

    python3 hwsw/equiv.py [--out results/81_verification/equivalence.json] [--work build/81/eqy]

Each case compares two versions of the demo register block (module demo_accel_regs) with eqy, from the OSS CAD Suite release
that CI pins (YosysHQ/oss-cad-suite-build 2026-11-12; set FDA_OSS_CAD to its folder, or have eqy, sby and yosys on PATH):

  house_before_after_73   the committed block before brief 73 (interface profiles) and after it, house profile. Expected
                          equivalent: the generator's change added comment lines and a profile banner only.
  house_vs_amd_compatible two profiles that are meant to differ (the amd_compatible one leaves the error-capture registers out).
  house_vs_strict         two profiles that are meant to differ (strict rejects partial, unaligned and reserved-bit writes).

A pair that is meant to be equivalent must prove, and a pair that is meant to differ must fail with the difference found.
Equivalence here is of the sequential design with registers matched by name, to the depth given in the .eqy file; eqy
does not check that two designs with different registers behave alike.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("house_before_after_73", "results/81_verification/demo_accel_regs_before_73.sv", "hwsw/examples/generated/demo_accel_regs.sv", True),
    ("house_vs_amd_compatible", "results/73_profiles/generated/house/demo_accel_regs.sv",
     "results/73_profiles/generated/amd_compatible/demo_accel_regs.sv", False),
    ("house_vs_strict", "results/73_profiles/generated/house/demo_accel_regs.sv",
     "results/73_profiles/generated/strict/demo_accel_regs.sv", False),
]
TOP = "demo_accel_regs"
DEPTH = 5


def eqy_text(gold: str, gate: str) -> str:
    return f"""[gold]
read_verilog -sv {gold}
prep -top {TOP}

[gate]
read_verilog -sv {gate}
prep -top {TOP}

[strategy sby]
use sby
depth {DEPTH}
engine smtbmc z3
"""


def tool_line(exe: str) -> str:
    out = subprocess.run([exe, "-V"], capture_output=True, text=True)
    return (out.stdout or out.stderr).strip().splitlines()[0]


def run_case(name: str, gold: str, gate: str, expect_equal: bool, work: Path) -> dict:
    d = work / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    shutil.copy(ROOT / gold, d / "gold.sv")
    shutil.copy(ROOT / gate, d / "gate.sv")
    (d / f"{name}.eqy").write_text(eqy_text("gold.sv", "gate.sv"))
    t0 = time.time()
    p = subprocess.run(["eqy", "-f", f"{name}.eqy"], cwd=d, capture_output=True, text=True)
    out = p.stdout + p.stderr
    (d / "eqy.log").write_text(out)
    equal = "Successfully proved designs equivalent" in out
    failed = sorted(set(re.findall(r"Failed to prove equivalence of (\S+)", out)))
    unproven = re.findall(r"(\d+) unproven", out)
    return {"case": name, "gold": gold, "gate": gate, "expected_equivalent": expect_equal, "equivalent": equal,
            "as_expected": equal == expect_equal, "unproven_partitions": failed, "seconds": round(time.time() - t0, 1),
            "returncode": p.returncode, "unproven_lines": unproven}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "results/81_verification/equivalence.json")
    ap.add_argument("--work", type=Path, default=ROOT / "build/81/eqy")
    a = ap.parse_args(argv)
    cad = os.environ.get("FDA_OSS_CAD")
    if cad:
        os.environ["PATH"] = f"{cad}/bin:" + os.environ["PATH"]
    for exe in ("eqy", "sby", "yosys"):
        if not shutil.which(exe):
            print(f"{exe} not found: set FDA_OSS_CAD to the OSS CAD Suite folder", file=sys.stderr)
            return 2
    res = {"tool": {"yosys": tool_line("yosys"), "eqy": "eqy from the same OSS CAD Suite release"}, "depth": DEPTH, "top": TOP,
           "cases": [run_case(*c, a.work) for c in CASES]}
    res["all_as_expected"] = all(c["as_expected"] for c in res["cases"])
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    for c in res["cases"]:
        print(f"{c['case']:26s} equivalent={c['equivalent']} expected={c['expected_equivalent']} {c['seconds']}s")
    return 0 if res["all_as_expected"] else 1


if __name__ == "__main__":
    sys.exit(main())
