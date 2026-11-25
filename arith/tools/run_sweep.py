#!/usr/bin/env python3
"""Clock sweep for the arithmetic points whose Fmax is only a lower bound (brief 166, follow-up 1 of brief 160).

    python3 -m arith.tools.run_sweep list
    python3 -m arith.tools.run_sweep run [--only fn/variant/part] [--part a7|k26] [--claim]

A point whose routed WNS is positive at the build file's clock has Fmax >= 1000 / (clock - WNS), nothing more. For each such point the sweep
re-runs it at a tighter clock, T' = FACTOR * (T - WNS) (FACTOR 0.6, floor 1.0 ns); if WNS is still positive it tightens again from the new
(T' - WNS'), up to ROUNDS rounds. A point is MEASURED when some round gives WNS <= 0 (Fmax = 1000 / (T' - WNS'), the same definition as the
brief-160 records); it is BRACKETED when no round does (the last round's bound stands, lower_bound stays true). Every round is kept.
One Vivado session (flow/ipchar.tcl, one thread) per (function, variant, part) and round, each under a heavy slot (prefix 166).
Records: arith/<fn>/verif/results/vivado_sweep_<variant>_<part>.json (never merged into the brief-160 record).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import ipchar  # noqa: E402
from arith.tools import run_vivado_ooc as R  # noqa: E402

FACTOR, FLOOR, ROUNDS, PEAK_G = 0.6, 1.0, 3, 4
SW = R.WORK.parent / "arith_sweep"


def positive_points() -> list[dict]:
    out = []
    for f in sorted(ROOT.glob("arith/*/verif/results/vivado_ooc_*.json")):
        d = json.loads(f.read_text())
        pts = [p for p in d["points"] if p["status"] == "ok" and p["wns_ns"] is not None and p["wns_ns"] > 0]
        if pts:
            out.append({"fn": d["function"], "variant": d["variant"], "part_key": d["part_key"], "part": d["part"], "top": d["top"],
                        "build_file": d["build_file"], "clock_ns": d["clock_ns"], "points": pts, "tool0": d["tool"]})
    return out


def srcs(build_file: str) -> list[str]:
    import yaml
    return R.sources(yaml.safe_load((ROOT / build_file).read_text()))


def sdir(s, g, rnd):
    return SW / s["fn"] / s["variant"] / s["part_key"] / R.pid(g) / f"r{rnd}"


def run_round(s: dict, todo: list[dict], rnd: int) -> None:
    batch = SW / "batch" / s["fn"] / s["variant"] / s["part_key"] / f"r{rnd}"
    lines = [f"set ipchar(part) {s['part']}", f"set ipchar(sources) {ipchar.tcl_list(srcs(s['build_file']))}", "set ipchar(jobs) {}"]
    for p in todo:
        d = sdir(s, p["generics"], rnd)
        for mk in ("done.txt", "error.txt"):
            (d / mk).unlink(missing_ok=True)
        lines.append("lappend ipchar(jobs) " + ipchar.tcl_list([f"{R.sid(s)}/{R.pid(p['generics'])}/r{rnd}", s["top"], str(d), p["try_ns"], R.tcl_gen(p["generics"])]))
    batch.mkdir(parents=True, exist_ok=True)
    (batch / "jobs.tcl").write_text("\n".join(lines) + "\n")
    now = datetime.datetime.now()
    text = f"166: Vivado impl OOC sweep {R.sid(s)} r{rnd}, {now:%H:%M}, expected end {(now + datetime.timedelta(minutes=max(8, 3 * len(todo)))):%H:%M}, peak {PEAK_G}G"
    lock = R.take_slot(text)
    try:
        unit = f"fda-sweep-{os.getpid()}-{int(time.time())}"
        cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", f"MemoryMax={PEAK_G + 2}G", "nice", "-n", "15",
               ipchar.vivado(), "-mode", "batch", "-nojournal", "-log", str(batch / "vivado.log"), "-source", str(ROOT / "flow" / "ipchar.tcl"),
               "-tclargs", str(batch / "jobs.tcl")]
        subprocess.Popen(cmd, cwd=batch, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait()
    finally:
        R.release(lock, "166")


def sweep_session(s: dict) -> Path:
    for p in s["points"]:
        p["rounds"] = []
        p["try_ns"] = max(FLOOR, round(FACTOR * (s["clock_ns"] - p["wns_ns"]), 3))
        p["done"] = False
    for rnd in range(1, ROUNDS + 1):
        todo = [p for p in s["points"] if not p["done"]]
        if not todo:
            break
        run_round(s, todo, rnd)
        for p in todo:
            d = sdir(s, p["generics"], rnd)
            try:
                r = ipchar.parse(d, p["try_ns"])
            except Exception as e:  # noqa: BLE001
                r = {"status": f"parse error {e}"}
            ent = {"round": rnd, "clock_ns": p["try_ns"], "status": r.get("status")}
            if r.get("status") == "ok":
                u = (d / "utilization.rpt").read_text()
                ent.update({k: r.get(k) for k in ("lut", "ff", "srl", "dsp", "bram_tiles", "wns_ns", "whs_ns", "fmax_mhz")})
                ent["carry"] = R.prim(u, "CARRY4") + R.prim(u, "CARRY8")
                ent["runtime_s"] = int((d / "done.txt").read_text().strip())
                if r["wns_ns"] <= 0 or p["try_ns"] <= FLOOR:
                    p["done"] = True
                else:
                    p["try_ns"] = max(FLOOR, round(FACTOR * (p["try_ns"] - r["wns_ns"]), 3))
            else:
                p["done"] = True
            p["rounds"].append(ent)
    rows = []
    for p in s["points"]:
        last = p["rounds"][-1] if p["rounds"] else {}
        measured = last.get("status") == "ok" and last["wns_ns"] <= 0
        rows.append({"generics": p["generics"], "clock_ns_160": s["clock_ns"], "wns_ns_160": p["wns_ns"], "fmax_mhz_160_bound": p["fmax_mhz"],
                     "rounds": p["rounds"], "measured": measured, "bracketed": (not measured) and last.get("status") == "ok",
                     "fmax_mhz": last.get("fmax_mhz") if last.get("status") == "ok" else None,
                     "fmax_clock_ns": last.get("clock_ns"), "wns_ns": last.get("wns_ns")})
    out = {"schema": "fda-arith/vivado_sweep/1", "function": s["fn"], "variant": s["variant"], "part_key": s["part_key"], "part": s["part"], "top": s["top"],
           "tool": R.vivado_version(SW / "batch" / s["fn"] / s["variant"] / s["part_key"] / "r1"), "date": datetime.date.today().isoformat(), "brief": 166,
           "method": f"points with WNS > 0 in the brief-160 record re-run at T' = {FACTOR} * (T - WNS), floor {FLOOR} ns, up to {ROUNDS} rounds; measured when WNS <= 0; "
                     "Fmax = 1000 / (T' - WNS'), routed, out of context, one run per round",
           "build_file": s["build_file"], "points": rows}
    f = ROOT / "arith" / s["fn"] / "verif" / "results" / f"vivado_sweep_{s['variant']}_{s['part_key']}.json"
    f.write_text(json.dumps(out, indent=1) + "\n")
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "run"])
    ap.add_argument("--only", default="")
    ap.add_argument("--part", default="")
    ap.add_argument("--claim", action="store_true")
    ap.add_argument("--reverse", action="store_true")
    a = ap.parse_args()
    ss = [s for s in positive_points() if R.sid(s).startswith(a.only) and (not a.part or s["part_key"] == a.part)]
    if a.reverse:
        ss.reverse()
    if a.cmd == "list":
        for s in ss:
            print(R.sid(s), len(s["points"]), "points")
        print(sum(len(s["points"]) for s in ss), "points in", len(ss), "sessions")
        return 0
    for s in ss:
        if a.claim:
            c = SW / "claims" / R.sid(s).replace("/", "__")
            c.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(c, "x") as fh:
                    fh.write(str(os.getpid()))
            except FileExistsError:
                continue
        print("wrote", sweep_session(s).relative_to(ROOT), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
