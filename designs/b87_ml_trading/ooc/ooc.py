#!/usr/bin/env python3
"""Post-route, out-of-context cost and clock of each decision arm on the K26 (xck26-sfvc784-2LV-c), Vivado 2026.1.

    python3 -m designs.b87_ml_trading.ooc.ooc [--arms gbt_comb lutnet ...] [--start 2.0] [--passes 4] [--dry-run]

Search for the clock each arm closes at: pass 1 builds every arm at --start ns; each later pass rebuilds only the
arms that have not yet closed, at the period the last pass's WNS implies (period - WNS, rounded up to 0.05 ns). An
arm that closes (WNS >= 0, WHS >= 0) at a period is recorded with that period; it is not tried faster again, so the
recorded clock is a closed point, not a bound. Each pass is one Vivado batch session in a memory-capped scope
(MemoryMax=6G, one thread, nice 15). Results: results/b87/ooc/<arm>.json, run directories build/b87/ooc/.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from flow.ipchar import _row, tcl_list, vivado  # noqa: E402

D = Path(__file__).resolve().parents[1]
PART = "xck26-sfvc784-2LV-c"
BUILD = ROOT / "build" / "b87" / "ooc"
OUT = ROOT / "results" / "b87" / "ooc"
GEN = D / "rtl" / "gen"
HLS_V = ROOT / "build" / "b87" / "hls4ml_rtl"       # the Verilog Vitis HLS wrote (copied there by the hls step)

WRAP = """// ooc_wrap for {arm}: an input register for the features (the producer's register), then the arm.
module ooc_wrap (input logic clk, input logic rst, input logic in_v, input logic [37:0] in_f,
                 output logic out_v, output logic [1:0] out_cls);
    logic v_q;
    logic [37:0] f_q;
    always_ff @(posedge clk) begin
        f_q <= in_f;
        v_q <= in_v;
    end
    {arm} u_arm (.clk, .rst, .in_v(v_q), .in_f(f_q), .out_v, .out_cls);
endmodule
"""


def arm_sources(arm: str) -> list[str]:
    if arm == "mlp_hls4ml":
        return sorted(str(p) for p in HLS_V.glob("*.v")) + [str(D / "rtl" / "mlp_hls4ml_wrap.sv")]
    return [str(GEN / f"{arm}.sv")]


def parse(wd: Path, clock_ns: float) -> dict:
    if (wd / "error.txt").exists():
        return {"status": "error: " + (wd / "error.txt").read_text().strip()[:300]}
    if not (wd / "done.txt").exists():
        return {"status": "not run"}
    u = (wd / "utilization.rpt").read_text()
    t = (wd / "timing_summary.rpt").read_text()
    m = re.search(r"WNS\(ns\)\s+TNS\(ns\).*?\n\s*-+.*?\n\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s+(-?\d+\.\d+)", t, re.S)
    r = {"status": "ok", "clock_ns": clock_ns,
         "lut": _row(u, "CLB LUTs"), "ff": _row(u, "CLB Registers"), "carry8": _row(u, "CARRY8"),
         "dsp": _row(u, "DSPs"), "bram_tiles": _row(u, "Block RAM Tile"),
         "wns_ns": float(m.group(1)) if m else None, "whs_ns": float(m.group(3)) if m else None,
         "wpws_ns": float(m.group(5)) if m else None,
         "build_seconds": int((wd / "done.txt").read_text().strip())}
    r["closed"] = r["wns_ns"] is not None and r["wns_ns"] >= 0 and r["whs_ns"] >= 0 and r["wpws_ns"] >= 0
    return r


def run_pass(jobs: list[tuple[str, float]], tag: str, dry: bool) -> dict:
    batch = BUILD / tag
    batch.mkdir(parents=True, exist_ok=True)
    lines = [f"set ooc(part) {PART}", "set ooc(jobs) {}"]
    wds = {}
    for arm, ck in jobs:
        wd = batch / f"{arm}_{ck:.2f}"
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "ooc_wrap.sv").write_text(WRAP.format(arm=arm if arm != "mlp_hls4ml" else "mlp_hls4ml_wrap"))
        for mk in ("done.txt", "error.txt"):
            (wd / mk).unlink(missing_ok=True)
        lines.append("lappend ooc(jobs) " + tcl_list([arm, "ooc_wrap", str(wd), ck,
                                                       arm_sources(arm) + [str(wd / "ooc_wrap.sv")]]))
        wds[arm] = (wd, ck)
    (batch / "jobs.tcl").write_text("\n".join(lines) + "\n")
    if dry:
        print((batch / "jobs.tcl").read_text())
        return {}
    unit = f"b87-ooc-{os.getpid()}-{tag}"
    cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", "MemoryMax=6G", "nice", "-n", "15",
           vivado(), "-mode", "batch", "-nojournal", "-log", str(batch / "vivado.log"),
           "-source", str(D / "ooc" / "ooc.tcl"), "-tclargs", str(batch / "jobs.tcl")]
    print(f"ooc: pass {tag}: {len(jobs)} jobs, scope {unit}", flush=True)
    subprocess.run(cmd, cwd=batch)
    return {arm: parse(wd, ck) for arm, (wd, ck) in wds.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="*", default=["imb_rule", "gbt_comb", "gbt_pipe", "mlp_hand", "lutnet"])
    ap.add_argument("--start", type=float, default=2.0)
    ap.add_argument("--passes", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="forget earlier passes (the arm's RTL changed)")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    hist = {arm: [] for arm in a.arms}
    for arm in a.arms:                       # keep the passes of earlier searches (same RTL unless --fresh)
        f = OUT / f"{arm}.json"
        if f.exists() and not a.fresh:
            hist[arm] = json.loads(f.read_text())["passes"]
    todo = {arm: a.start for arm in a.arms}
    for p in range(a.passes):
        if not todo:
            break
        tag = f"pass{p + 1}"
        k = 2
        while (BUILD / tag).exists() and p == 0:
            tag, k = f"run{k}_pass1", k + 1
        if p > 0:
            tag = tag_base + f"_pass{p + 1}"
        tag_base = tag.rsplit("_pass", 1)[0] if p == 0 else tag_base
        res = run_pass(sorted(todo.items()), tag, a.dry_run)
        if a.dry_run:
            return 0
        nxt = {}
        for arm, r in res.items():
            hist[arm].append(r)
            if r["status"] != "ok":
                continue
            t = math.ceil((r["clock_ns"] - min(r["wns_ns"], 2 * (r["wpws_ns"] or 0.0))) * 20 - 1e-6) / 20
            if r["closed"]:                  # closed with slack to spare: try the period the slack implies
                fails = [x["clock_ns"] for x in hist[arm] if x.get("status") == "ok" and not x["closed"]]
                if t <= r["clock_ns"] - 0.05 and not any(f >= t for f in fails):
                    nxt[arm] = t
                continue
            closed = [x["clock_ns"] for x in hist[arm] if x.get("closed")]
            t = t + (0.05 if p >= 1 else 0.0)
            if not closed or t < min(closed):
                nxt[arm] = t
        todo = nxt
    ver = "unknown"
    for log in sorted(BUILD.glob("pass*/vivado.log")):
        m = re.search(r"Vivado v(\S+) \(64-bit\)", log.read_text())
        if m:
            ver = m.group(1)
    for arm, h in hist.items():
        closed = [r for r in h if r.get("closed")]
        best = min(closed, key=lambda r: r["clock_ns"]) if closed else None
        rec = {"arm": arm, "part": PART, "tool": f"Vivado {ver}", "flow": "out of context, post-route, one thread",
               "wrapper": "an input register for the features before the arm (ooc_wrap); the arm's own output register",
               "closed_at_ns": best["clock_ns"] if best else None,
               "closed_at_mhz": round(1000 / best["clock_ns"], 1) if best else None,
               "at_closed_clock": best, "passes": h}
        (OUT / f"{arm}.json").write_text(json.dumps(rec, indent=1))
        print(arm, rec["closed_at_ns"], best and {k: best[k] for k in ("lut", "ff", "dsp", "wns_ns")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
