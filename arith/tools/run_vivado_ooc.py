#!/usr/bin/env python3
"""Run the prepared out-of-context Vivado builds of the arithmetic library (brief 160) and record the results.

    python3 -m arith.tools.run_vivado_ooc list
    python3 -m arith.tools.run_vivado_ooc run [--only fn/variant/part] [--shard I/N] [--dry-run]
    python3 -m arith.tools.run_vivado_ooc parse            # rebuild the records from earlier reports, run nothing

Reads every arith/<fn>/build/<variant>[/<a7|k26>]/build.yaml (brief 139a layout: one file, `ooc.parts` has both parts; brief 139b layout:
one file per part, `clock_ns` and `points[].generics`). One Vivado session (flow/ipchar.tcl, one thread) per (function, variant, part),
one job per point, each at the build file's clock. The session holds a heavy slot (take_heavy_slot.sh) and runs under systemd-run with a
memory cap. Records: arith/<fn>/verif/results/vivado_ooc_<variant>_<part>.json (one file per run, never merged into another).
Fmax = 1000 / (clock_ns - WNS) from the routed design (an estimate from one run at that clock; flow/ipchar.py's parse()).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import ipchar  # noqa: E402

HANDOFF = Path("/home/brendan/Claude_sandbox/_handoff")
WORK = ROOT / "build" / "arith_ooc"
PEAK_G = 4
FN_ORDER = ["adder", "lzc_norm", "fxp_round", "isqrt", "divider", "mac", "multiplier"]


def build_files() -> list[Path]:
    return sorted(ROOT.glob("arith/*/build/*/build.yaml")) + sorted(ROOT.glob("arith/*/build/*/*/build.yaml"))


def sources(y: dict) -> list[str]:
    out = []
    for s in y["sources"]:
        out += sorted(str(p) for p in ROOT.glob(s)) if any(c in s for c in "*?[") else [str(ROOT / s)]
    return out


def sessions() -> list[dict]:
    """One entry per (function, variant, part): its sources, top, clock and points."""
    out = []
    for f in build_files():
        y = yaml.safe_load(f.read_text())
        fn, var = y["function"], y["variant"]
        if "ooc" in y:                                    # 139a
            for key, pd in y["ooc"]["parts"].items():
                out.append({"fn": fn, "variant": var, "part_key": key, "part": pd["part"], "clock_ns": float(pd["clock_ns"]), "top": y["top"],
                            "sources": sources(y), "points": [{"generics": p, "expected": None} for p in y["points"]],
                            "expected_text": (y.get("expected_primitives") or {}).get(key), "file": f})
        else:                                             # 139b
            key = f.parent.name
            out.append({"fn": fn, "variant": var, "part_key": key, "part": y["part"], "clock_ns": float(y["clock_ns"]), "top": y["top"],
                        "sources": sources(y), "points": [{"generics": p["generics"], "expected": p.get("expected_primitives")} for p in y["points"]],
                        "expected_text": None, "file": f})
    return out


def sid(s: dict) -> str:
    return f"{s['fn']}/{s['variant']}/{s['part_key']}"


def pid(g: dict) -> str:
    return "_".join(f"{k}{v}" for k, v in sorted(g.items()))


def wd(s: dict, g: dict) -> Path:
    return WORK / s["fn"] / s["variant"] / s["part_key"] / pid(g)


def order(ss: list[dict]) -> list[dict]:
    return sorted(ss, key=lambda s: (FN_ORDER.index(s["fn"]) if s["fn"] in FN_ORDER else 99, s["fn"], s["variant"], s["part_key"]))


# ---- parsing -------------------------------------------------------------------------------------------------------
def prim(txt: str, name: str):
    m = re.search(rf"^\|\s*{re.escape(name)}\s*\|\s*(\d+)\s*\|", txt, re.M)
    return int(m.group(1)) if m else 0


def parse_point(s: dict, p: dict) -> dict:
    d = wd(s, p["generics"])
    r = ipchar.parse(d, s["clock_ns"])
    r["generics"] = p["generics"]
    if r["status"] != "ok":
        return r
    u = (d / "utilization.rpt").read_text()
    r["carry4"], r["carry8"] = prim(u, "CARRY4"), prim(u, "CARRY8")
    r["carry"] = r["carry4"] + r["carry8"]
    r["dsp"] = r.get("dsp") or 0
    r["bram_tiles"] = r.get("bram_tiles") or 0
    rt = (d / "timing_worst_setup.rpt").read_text()
    m = re.search(r"Logic Levels:\s+(\d+)", rt)
    r["logic_levels"] = int(m.group(1)) if m else None
    r["runtime_s"] = int((d / "done.txt").read_text().strip())
    r["expected"] = p["expected"]
    return r


def vivado_version(batch: Path) -> str:
    lg = batch / "vivado.log"
    if lg.exists():
        m = re.search(r"Vivado v(\S+) \(64-bit\)", lg.read_text()[:4000])
        b = re.search(r"SW Build (\d+)", lg.read_text()[:4000])
        if m:
            return f"Vivado {m.group(1)}" + (f" (build {b.group(1)})" if b else "")
    return "Vivado (version not read)"


def record(s: dict, batch: Path, date: str) -> Path:
    rows = [parse_point(s, p) for p in s["points"]]
    out = {"schema": "fda-arith/vivado_ooc/1", "function": s["fn"], "variant": s["variant"], "part_key": s["part_key"], "part": s["part"],
           "clock_ns": s["clock_ns"], "top": s["top"], "tool": vivado_version(batch), "date": date, "brief": 160,
           "flow": "out-of-context synth_design, opt_design, place_design, route_design; one thread; clock on port clk only (the wrapper registers every "
                   "input and output; I/O paths unconstrained); Fmax = 1000 / (clock_ns - WNS) after routing, one run at that clock; power: vectorless",
           "expected_text": s["expected_text"], "build_file": str(s["file"].relative_to(ROOT)), "points": rows}
    f = ROOT / "arith" / s["fn"] / "verif" / "results" / f"vivado_ooc_{s['variant']}_{s['part_key']}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1) + "\n")
    return f


# ---- running -------------------------------------------------------------------------------------------------------
def tcl_gen(g: dict) -> list:
    out = []
    for k, v in g.items():
        out += [k, int(v) if isinstance(v, bool) else v]
    return out


def write_jobs(s: dict, path: Path) -> None:
    lines = [f"set ipchar(part) {s['part']}", f"set ipchar(sources) {ipchar.tcl_list(s['sources'])}", "set ipchar(jobs) {}"]
    for p in s["points"]:
        d = wd(s, p["generics"])
        lines.append("lappend ipchar(jobs) " + ipchar.tcl_list([f"{sid(s)}/{pid(p['generics'])}", s["top"], str(d), s["clock_ns"], tcl_gen(p["generics"])]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def take_slot(text: str) -> str:
    while True:
        r = subprocess.run([str(HANDOFF / "take_heavy_slot.sh"), text], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
        time.sleep(30)


def release(lock: str, prefix: str) -> None:
    p = Path(lock)
    if p.exists() and p.read_text().startswith(prefix + ":"):
        p.unlink()


def run_session(s: dict, deadline: float | None) -> int:
    batch = WORK / "batch" / s["fn"] / s["variant"] / s["part_key"]
    write_jobs(s, batch / "jobs.tcl")
    for p in s["points"]:
        for mk in ("done.txt", "error.txt"):
            (wd(s, p["generics"]) / mk).unlink(missing_ok=True)
    now = datetime.datetime.now()
    est = max(8, 4 * len(s["points"]))
    text = f"160: Vivado impl OOC {sid(s)}, {now:%H:%M}, expected end {(now + datetime.timedelta(minutes=est)):%H:%M}, peak {PEAK_G}G"
    lock = take_slot(text)
    try:
        if deadline and time.time() > deadline:
            print("deadline reached, not starting", sid(s))
            return 99
        unit = f"fda-arith-{os.getpid()}-{int(time.time())}"
        cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", f"MemoryMax={PEAK_G + 2}G", "nice", "-n", "10",
               ipchar.vivado(), "-mode", "batch", "-nojournal", "-log", str(batch / "vivado.log"),
               "-source", str(ROOT / "flow" / "ipchar.tcl"), "-tclargs", str(batch / "jobs.tcl")]
        proc = subprocess.Popen(cmd, cwd=batch, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc.wait()
        rc = proc.returncode
    finally:
        release(lock, "160")
    print(f"{sid(s)}: exit {rc}; wrote", record(s, batch, datetime.date.today().isoformat()).relative_to(ROOT), flush=True)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "run", "parse"])
    ap.add_argument("--only", default="", help="function/variant/part_key prefix")
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--deadline", default="", help="HH:MM today: do not start a session after this time")
    a = ap.parse_args()
    ss = [s for s in order(sessions()) if sid(s).startswith(a.only)]
    i, n = map(int, a.shard.split("/"))
    ss = [s for k, s in enumerate(ss) if k % n == i]
    if a.cmd == "list" or a.dry_run:
        for s in ss:
            print(sid(s), s["part"], s["clock_ns"], len(s["points"]), "points")
        print(sum(len(s["points"]) for s in ss), "jobs in", len(ss), "sessions")
        return 0
    if a.cmd == "parse":
        for s in ss:
            batch = WORK / "batch" / s["fn"] / s["variant"] / s["part_key"]
            if any((wd(s, p["generics"]) / "done.txt").exists() for p in s["points"]):
                print("wrote", record(s, batch, datetime.date.today().isoformat()).relative_to(ROOT))
        return 0
    dl = None
    if a.deadline:
        h, m = map(int, a.deadline.split(":"))
        dl = datetime.datetime.combine(datetime.date.today(), datetime.time(h, m)).timestamp()
    for s in ss:
        if dl and time.time() > dl:
            print("deadline reached; stopping before", sid(s))
            break
        run_session(s, dl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
