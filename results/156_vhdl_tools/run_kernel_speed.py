#!/usr/bin/env python3
"""Brief 156: simulator kernel speed with no cocotb in the loop: rtl/fir_tb.vhd (pure VHDL, LFSR stimulus, output checksum).

    python3 results/156_vhdl_tools/run_kernel_speed.py [--cycles 300000] [--reps 3] [--out kernel_speed.json]

Reports build time, run time (median of reps) and the checksum line; every simulator must print the same checksum.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_sims as R  # noqa: E402

FILES = [R.HERE / "rtl" / f for f in ("fir_pkg.vhd", "fir_add_tree.vhd", "fir16.vhd", "fir_tb.vhd")]


def cmds(s: R.Sim, wd: Path, cycles: int):
    fs = [str(f) for f in FILES]
    g = f"-gCYCLES={cycles}"
    if s.kind in ("ghdl-mcode", "ghdl-llvm"):
        build = [[s.exe, "-a", "--std=08", f"--workdir={wd}"] + fs, [s.exe, "-e", "--std=08", f"--workdir={wd}", "fir_tb"]]
        run = [s.exe, "-r", "--std=08", f"--workdir={wd}", "fir_tb", g]
        return build, run
    w = f"--work=work:{wd}/work"
    b = [[s.exe, "--std=2008", w, "-a"] + fs]
    if s.kind == "nvc-aot":
        b.append([s.exe, "--std=2008", w, "-e", g, "fir_tb"])
        return b, [s.exe, "--std=2008", w, "-r", "fir_tb"]
    return b, [s.exe, "--std=2008", w, "-e", "--no-save", g, "fir_tb", "-r"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=300000)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", default=str(R.HERE / "kernel_speed.json"))
    ap.add_argument("--work", default=str(R.ROOT / "build" / "156_kernel"))
    a = ap.parse_args()
    res = {"date": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "cycles": a.cycles, "reps": a.reps, "sims": {}}
    for s in R.sims([]):
        wd = Path(a.work) / s.name
        if wd.exists():
            shutil.rmtree(wd)
        wd.mkdir(parents=True)
        b, r = cmds(s, wd, a.cycles)
        t0 = time.perf_counter()
        for c in b:
            p = subprocess.run(c, cwd=wd, env=s.env, capture_output=True, text=True)
            if p.returncode:
                res["sims"][s.name] = {"error": (p.stderr + p.stdout)[-400:]}
                break
        else:
            build_s = time.perf_counter() - t0
            runs, lines = [], set()
            for _ in range(a.reps):
                t0 = time.perf_counter()
                p = subprocess.run(r, cwd=wd, env=s.env, capture_output=True, text=True)
                runs.append(time.perf_counter() - t0)
                m = re.search(r"CHECKSUM=\d+ OUTPUTS=\d+ SAT='\d'", p.stdout + p.stderr)
                lines.add(m.group(0) if m else f"no checksum (rc {p.returncode})")
            res["sims"][s.name] = {"build_s": build_s, "run_s": runs, "run_s_median": statistics.median(runs), "result": sorted(lines),
                                   "clocks_per_s": a.cycles / statistics.median(runs)}
            print(f"{s.name:20s} build {build_s:6.2f}  run {statistics.median(runs):7.2f}  {sorted(lines)}", flush=True)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
