#!/usr/bin/env python3
"""Mutation testing of a design's RTL (brief 04f): the independent measure of a bench's quality.

    python3 flow/mutate.py designs/t1_dimmer_counter [--json OUT] [--only name,name]

Each mutant in <design>/verif/mutants.yaml replaces one exact string in a copy of rtl/ (operator, constant,
condition and reset mutations); the real RTL is never touched. Each mutant is run twice, one seed:
  tests    the cocotb bench under Icarus (no assertions exist there): the bench's own score
  checkers the bench under Verilator with the bound checkers: tests plus assertions
A mutant is killed when the run fails; it is invalid (and excluded) when the copy does not build. Reports
score_pct = killed / valid for the bench alone, score_with_checkers_pct, and the surviving mutants by name.
Local-only by default (about 25 s a run, 2 runs a mutant); CI runs it on a schedule or manually.
Needs the simulators of flow/portability.py's environment: iverilog, and Verilator 5.036+ for cocotb 2 (SIM=verilator).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PY = os.environ.get("MUTATE_PYTHON", sys.executable)


def run(design: Path, mdir: Path, tag: str, sim: str) -> dict:
    env = dict(os.environ, SIM=sim, T1_SEEDS="1", T1_RTL_DIR=str(mdir), T1_RUN_TAG=tag)
    r = subprocess.run([PY, "-m", "pytest", "-q", "-x", str(design / "tests" / "test_t1_verif_rtl.py")],
                       capture_output=True, text=True, cwd=ROOT, env=env, timeout=1800)
    out = ROOT / "build" / "verif" / f"{sim}{tag}" / "seed1"
    built = (out / "results.xml").exists()
    log = (out / "sim.log").read_text(errors="replace") if (out / "sim.log").exists() else ""
    return {"built": built, "killed": r.returncode != 0, "assertion": "Assertion failed" in log}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("design")
    ap.add_argument("--json")
    ap.add_argument("--only")
    a = ap.parse_args()
    design = (ROOT / a.design).resolve()
    muts = yaml.safe_load((design / "verif" / "mutants.yaml").read_text())["mutants"]
    if a.only:
        muts = [m for m in muts if m["name"] in a.only.split(",")]
    rows = []
    for m in muts:
        d = ROOT / "build" / "mutants" / m["name"]
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        for f in (design / "rtl").glob("*.sv"):
            shutil.copy(f, d / f.name)
        src = (d / m["file"]).read_text()
        assert src.count(m["old"]) == 1, f"{m['name']}: old text occurs {src.count(m['old'])} times"
        (d / m["file"]).write_text(src.replace(m["old"], m["new"]))
        row = {"name": m["name"], "class": m["class"], "why": m["why"]}
        row["tests"] = run(design, d, f"_mut_{m['name']}", "icarus")
        row["checkers"] = run(design, d, f"_mut_{m['name']}", "verilator")
        valid = row["tests"]["built"] or row["checkers"]["built"]
        row["valid"] = valid
        row["status"] = "invalid" if not valid else ("killed" if row["tests"]["killed"] else
                        ("killed_by_checkers_only" if row["checkers"]["killed"] else "survived"))
        print(f"{m['name']:22s} {m['class']:10s} {row['status']}", flush=True)
        rows.append(row)
    valid = [r for r in rows if r["valid"]]
    bench_killed = [r for r in valid if r["tests"]["killed"]]
    all_killed = [r for r in valid if r["tests"]["killed"] or r["checkers"]["killed"]]
    res = {"design": design.name, "mutants": len(rows), "valid": len(valid),
           "killed_by_bench": len(bench_killed), "score_pct": round(100 * len(bench_killed) / max(1, len(valid)), 2),
           "killed_with_checkers": len(all_killed),
           "score_with_checkers_pct": round(100 * len(all_killed) / max(1, len(valid)), 2),
           "survivors": [r["name"] for r in valid if not r["tests"]["killed"]],
           "survivors_with_checkers": [r["name"] for r in valid if not (r["tests"]["killed"] or r["checkers"]["killed"])],
           "rows": rows}
    print(f"bench score {res['score_pct']}% ({len(bench_killed)}/{len(valid)}); with checkers {res['score_with_checkers_pct']}%")
    print("survivors (bench):", res["survivors"], " survivors (bench+checkers):", res["survivors_with_checkers"])
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
