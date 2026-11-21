#!/usr/bin/env python3
"""The partition sweep of brief 151: the points, the questions each answers, the Yosys area run (now) and the Vivado queue rows
(later). Vivado is not run here (decision 27, owner 2026-11-21: Vivado runs are queued).

    python3 partition/sweep.py --list                      # the points and which question each belongs to
    python3 partition/sweep.py --yosys results/b151/part_sys_yosys.json      # area from Yosys (synth_xilinx), no placement
    python3 partition/sweep.py --queue results/b151/partition_queue_rows.md  # the rows for vivado_later_queue.md
    python3 partition/sweep.py --run-point <name> [--dry-run]                # what the planner runs when a slot is free

Parts: xc7a100tcsg324-1 (Artix-7, the Nexys A7) and xck26-sfvc784-2LV-c (the K26 in the KR260). A target clock of 4.0 ns on the
first and 2.5 ns on the second is a starting point; every point records WNS, so Fmax = 1000 / (T - WNS) at that point.
Distance DIST is how far apart the first and last sub-module's pblocks are on the line from the lowest clock region to the highest
(0 = the same region, 0.5, 1 = opposite corners; -1 = no pblocks at all). The questions Q1-Q7 are written in docs/partitioning_study.md with their nulls."""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = {"a7": ("xc7a100tcsg324-1", 4.0, "xc7"), "k26": ("xck26-sfvc784-2LV-c", 2.5, "xcup")}
HS = {0: "FWD", 1: "SKID", 2: "FULL", 3: "HALF", 4: "COMB", 5: "PLAIN", 6: "CREDIT"}
BASE = dict(NM=8, W=64, D=2)


def point(q, part, hs, st, keep=0, retime=0, dist=1.0):
    name = f"{q}_{part}_{HS[hs].lower()}_s{st}_k{keep}_r{retime}_d{int(dist * 100):03d}"
    return dict(name=name, q=q, part=part, HS=hs, STAGES=st, KEEP=keep, RETIME=retime, DIST=dist, **BASE)


def points():
    P = []
    for part in PARTS:
        for st in (0, 1, 2, 3):                                 # Q1/Q2: boundary stages, skid buffer, three distances
            for dist in (0.0, 0.5, 1.0):
                P.append(point("q1", part, 1, st, dist=dist))
        for hs in (0, 1, 2, 3, 4, 5, 6):                        # Q4: handshake types at one and two stages, far apart
            for st in (1, 2):
                P.append(point("q4", part, hs, st))
        for keep in (0, 1):                                     # Q3: KEEP_HIERARCHY and retiming (plain and skid boundaries)
            for retime in (0, 1):
                for st in (0, 1, 2):
                    for hs in (5, 1):
                        if st == 0 and hs == 1:
                            continue
                        P.append(point("q3", part, hs, st, keep=keep, retime=retime))
        for st in (0, 1, 2):                                    # Q5: no pblocks at all (DIST -1): where the tool puts the sub-modules
            P.append(point("q5", part, 1, st, dist=-1.0))
        for nm in (4, 16):                                      # Q6: more sub-modules (compile time, reuse by cutting)
            p = point("q6", part, 1, 1)
            p["NM"] = nm
            p["name"] = p["name"] + f"_n{nm}"
            P.append(p)
    seen, out = set(), []
    for p in P:                                                 # a point that is the same as an earlier one is run once
        key = tuple((k, v) for k, v in p.items() if k not in ("name", "q"))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def yosys_points():
    """Area only: no placement, so no distance, no hierarchy keep, no retiming: handshake x boundary depth, Artix-7 family."""
    return [dict(HS=hs, STAGES=st, **BASE) for hs in range(7) for st in (1, 2, 3) if not (hs == 6 and st == 0)] + [dict(HS=1, STAGES=0, **BASE)]


def oss_bin() -> str:
    for c in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")):
        if c and (Path(c) / "bin" / "yosys").exists():
            return str(Path(c) / "bin")
    return ""


def yosys_area(p: dict, family: str) -> dict:
    files = ["partition/rtl/part_sys.sv", "partition/rtl/part_stage.sv", "ip_lib/pipe_reg/rtl/pipe_reg.sv",
             "ip_lib/pipe_reg/rtl/pipe_reg_slice.sv", "ip_lib/credit_chan/rtl/credit_chan.sv"]
    script = (f"plugin -i slang\nread_slang {' '.join(files)} --top part_sys -G NM={p['NM']} -G W={p['W']} -G D={p['D']} "
              f"-G HS={p['HS']} -G STAGES={p['STAGES']}\nsynth_xilinx -family {family} -flatten -top part_sys\nstat\n")
    with tempfile.TemporaryDirectory() as t:
        s = Path(t) / "a.ys"
        s.write_text(script)
        r = subprocess.run(["yosys", "-q", "-l", str(Path(t) / "log"), str(s)], cwd=ROOT, capture_output=True, text=True,
                           env=dict(os.environ, PATH=oss_bin() + os.pathsep + os.environ["PATH"]), timeout=900)
        log = (Path(t) / "log").read_text() if (Path(t) / "log").exists() else r.stderr
    last = log.rsplit("Number of cells", 1)[-1] if "Number of cells" in log else log.rsplit("cells\n", 1)[-1]
    cnt = {}
    for line in log.splitlines()[-60:]:
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit():
            cnt[parts[1]] = int(parts[0])
    lut = sum(v for k, v in cnt.items() if k.startswith("LUT"))
    ff = sum(v for k, v in cnt.items() if k.startswith("FD"))
    return add_derived({**p, "family": family, "lut": lut, "ff": ff, "carry": sum(v for k, v in cnt.items() if k.startswith("CARRY")),
                        "cells": cnt})


def add_derived(r: dict) -> dict:
    """Shift-register LUTs (SRL*) and LUT RAM (RAM*) are counted apart from LUT and FF: a data pipeline of three or more stages
    with no reset or enable is mapped to SRLs, which is why its FF count drops."""
    c = r["cells"]
    r["srl"] = sum(v for k, v in c.items() if k.startswith("SRL"))
    r["lutram"] = sum(v for k, v in c.items() if k.startswith("RAM"))
    r["boundary_lut_over_unpartitioned"] = None
    return r


GROUPS = {"q1": "Q1/Q2: boundary stages 0-3 of a skid buffer at three distances", "q4": "Q4: the seven boundary kinds at one and two stages, far apart",
          "q3": "Q3: KEEP_HIERARCHY and retiming, plain and skid boundaries, 0-2 stages", "q5": "Q5: no pblocks (free placement) with a skid boundary, 0-2 stages, to compare with q1",
          "q6": "Q6: 4 and 16 sub-modules (compile time)"}


def queue_rows() -> str:
    peak = subprocess.run([sys.executable, "/home/brendan/Claude_sandbox/_handoff/fpga_agent/resources/vivado_peak.py", "partition_sweep"],
                          capture_output=True, text=True).stdout.strip() or "peak 4G"
    peak = peak.split(" (")[0]
    L = []
    for q, what in GROUPS.items():
        for part in PARTS:
            n = sum(1 for p in points() if p["q"] == q and p["part"] == part)
            L.append(f"| 2026-11-21 | 151 | partition sweep group `{q}_{part}` ({n} points, one run each, in order): {what}; a synthetic system of 8 sub-modules "
                     f"(64-bit, logic depth 2) in pblocks from one corner of the device to the other; expected outcome per question: "
                     f"docs/partitioning_study.md; results to results/b151/vivado/ | {PARTS[part][0]} | "
                     f"`python3 /home/brendan/Claude_sandbox/_worktrees/151-partition/partition/sweep.py --run-group {q}_{part}` "
                     f"(one point: `--run-point <name>`; `--list` names them; `--dry-run` shows the command) | {peak} each, one at a time | queued |")
    return "\n".join(L) + "\n"


def run_point(name: str, dry: bool):
    p = next(q for q in points() if q["name"] == name)
    part, t, _ = PARTS[p["part"]]
    out = ROOT / "results" / "b151" / "vivado" / name
    env = dict(os.environ, PART=part, T_NS=str(t), HS=str(p["HS"]), STAGES=str(p["STAGES"]), KEEP=str(p["KEEP"]), RETIME=str(p["RETIME"]),
               DIST=str(p["DIST"]), NM=str(p["NM"]), W=str(p["W"]), D=str(p["D"]), OUT=str(out))
    cmd = ["systemd-run", "--user", "--scope", "-p", "MemoryMax=6G", "nice", "-n", "15", "/opt/Xilinx/2026.1/Vivado/bin/vivado",
           "-mode", "batch", "-nojournal", "-log", str(out / "vivado.log"), "-source", str(ROOT / "partition" / "run_point.tcl")]
    print(" ".join(cmd))
    print({k: env[k] for k in ("PART", "T_NS", "HS", "STAGES", "KEEP", "RETIME", "DIST", "NM")})
    if dry:
        return 0
    print("Take a heavy slot first (take_heavy_slot.sh, text with 'Vivado impl' and the declared peak) and release it after.")
    out.mkdir(parents=True, exist_ok=True)
    return subprocess.run(cmd, env=env).returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--yosys", default="")
    ap.add_argument("--yosys-update", default="", help="add the derived fields (srl, lutram, cost over the STAGES = 0 point) to an existing --yosys file")
    ap.add_argument("--queue", default="")
    ap.add_argument("--run-point", default="")
    ap.add_argument("--run-group", default="", help="q1_a7, q4_k26, ...: every point of the group, one after another")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.list:
        for p in points():
            print(p["name"])
        print(len(points()), "points")
    if a.yosys:
        res = [yosys_area(p, "xc7") for p in yosys_points()]
        res += [yosys_area(p, "xcup") for p in yosys_points() if p["HS"] in (1, 5, 6) and p["STAGES"] == 1]
        Path(a.yosys).parent.mkdir(parents=True, exist_ok=True)
        Path(a.yosys).write_text(json.dumps({"tool": "Yosys synth_xilinx (OSS CAD Suite), flattened, no placement", "points": res}, indent=1) + "\n")
        for r in res:
            print(r["family"], HS[r["HS"]], r["STAGES"], "LUT", r["lut"], "FF", r["ff"], "CARRY", r["carry"])
    if a.yosys_update:
        f = Path(a.yosys_update)
        d = json.loads(f.read_text())
        base = {r["family"]: r for r in d["points"] if r["STAGES"] == 0}
        for r in d["points"]:
            add_derived(r)
            b = base.get(r["family"]) or base["xc7"]
            r["boundary_lut_over_unpartitioned"] = r["lut"] - b["lut"]
        f.write_text(json.dumps(d, indent=1) + "\n")
    if a.queue:
        Path(a.queue).write_text(queue_rows())
    if a.run_point:
        return run_point(a.run_point, a.dry_run)
    if a.run_group:
        q, part = a.run_group.split("_")
        rc = 0
        for p in points():
            if p["q"] == q and p["part"] == part:
                rc |= run_point(p["name"], a.dry_run)
        return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
