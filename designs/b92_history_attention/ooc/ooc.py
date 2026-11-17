#!/usr/bin/env python3
"""Post-route, out-of-context cost and clock of each brief 92 network on a part, Vivado 2026.1, by the brief 87
method (designs/b87_ml_trading/ooc/ooc.py, whose Tcl and parser this reuses): the arm inside the 87 `ooc_wrap` (an
input register for the features), a clock on port clk, synthesis, placement and routing in one Vivado batch session
per pass; the search moves the period by what WNS and pulse width imply until the arm closes (setup, hold and pulse
width all met) at the fastest period it was tried at.

    python3 -m designs.b92_history_attention.ooc.ooc --part xck26-sfvc784-2LV-c --arms b92_a1_decay b92_a2_win8 [--start 2.0]

Results: results/b92/ooc/<part>/<arm>.json; reports under results/b92/ooc/<part>/reports/<arm>/.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from designs.b87_ml_trading.ooc.ooc import parse  # noqa: E402
from flow.ipchar import _row, tcl_list, vivado  # noqa: E402

D = Path(__file__).resolve().parents[1]
TCL = ROOT / "designs" / "b87_ml_trading" / "ooc" / "ooc.tcl"
GEN = D / "rtl" / "gen"
PARTS = {"xck26-sfvc784-2LV-c": "k26", "xc7a100tcsg324-1": "a7"}


WRAP = """// ooc_wrap for {arm}: an input register for the packed event (the producer's register), then the arm.
module ooc_wrap (input logic clk, input logic rst, input logic in_v, input logic [{hi}:0] in_f,
                 output logic out_v, output logic [1:0] out_cls);
    logic v_q;
    logic [{hi}:0] f_q;
    always_ff @(posedge clk) begin
        f_q <= in_f;
        v_q <= in_v;
    end
    {arm} u_arm (.clk, .rst, .in_v(v_q), .in_f(f_q), .out_v, .out_cls);
endmodule
"""


def sources(arm: str) -> list[str]:
    net = GEN / f"{arm}_net.sv"
    return ([str(net)] if net.exists() else []) + [str(GEN / f"{arm}.sv")]


def width(arm: str) -> int:
    return 38 if arm == "b92_ref_current" else 51


def fix_util(r: dict) -> dict:
    """The 87 parser reads UltraScale+ names (CLB LUTs, CLB Registers); 7-series reports say Slice LUTs and Slice
    Registers. Fill those from the pass's own report."""
    wd = r.get("wd")
    if r.get("status") == "ok" and r.get("lut") is None and wd and (Path(wd) / "utilization.rpt").exists():
        u = (Path(wd) / "utilization.rpt").read_text()
        r["lut"], r["ff"] = _row(u, "Slice LUTs"), _row(u, "Slice Registers")
        r["carry8"] = r.get("carry8") if r.get("carry8") is not None else _row(u, "CARRY4")
    return r


def run_pass(part, jobs, tag, unit_tag):
    batch = ROOT / "build" / "b92" / "ooc" / PARTS[part] / tag
    batch.mkdir(parents=True, exist_ok=True)
    lines = [f"set ooc(part) {part}", "set ooc(jobs) {}"]
    wds = {}
    for arm, ck in jobs:
        wd = batch / f"{arm}_{ck:.2f}"
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "ooc_wrap.sv").write_text(WRAP.format(arm=arm, hi=width(arm) - 1))
        for mk in ("done.txt", "error.txt"):
            (wd / mk).unlink(missing_ok=True)
        lines.append("lappend ooc(jobs) " + tcl_list([arm, "ooc_wrap", str(wd), ck, sources(arm) + [str(wd / "ooc_wrap.sv")]]))
        wds[arm] = (wd, ck)
    (batch / "jobs.tcl").write_text("\n".join(lines) + "\n")
    unit = f"b92-ooc-{unit_tag}-{PARTS[part]}-{tag}"
    cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", "MemoryMax=6G", "nice", "-n", "15",
           vivado(), "-mode", "batch", "-nojournal", "-log", str(batch / "vivado.log"), "-source", str(TCL),
           "-tclargs", str(batch / "jobs.tcl")]
    print(f"ooc: {part} pass {tag}: {len(jobs)} jobs, scope {unit}", flush=True)
    subprocess.run(cmd, cwd=batch)
    m = re.search(r"Vivado v(\S+) \(64-bit\)", (batch / "vivado.log").read_text()) if (batch / "vivado.log").exists() else None
    return {arm: fix_util(dict(parse(wd, ck), wd=str(wd))) for arm, (wd, ck) in wds.items()}, (m.group(1) if m else "unknown")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=sorted(PARTS))
    ap.add_argument("--arms", nargs="+", required=True)
    ap.add_argument("--start", type=float, default=2.0)
    ap.add_argument("--passes", type=int, default=4)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--rewrite", action="store_true", help="no Vivado: re-read the recorded passes and rewrite the JSON")
    a = ap.parse_args(argv)
    out = ROOT / "results" / "b92" / "ooc" / PARTS[a.part]
    out.mkdir(parents=True, exist_ok=True)
    hist = {arm: [] for arm in a.arms}
    for arm in a.arms:
        f = out / f"{arm}.json"
        if f.exists() and not a.fresh:
            hist[arm] = [fix_util(r) for r in json.loads(f.read_text())["passes"]]
    # an arm whose earlier search already closed is not rebuilt (same RTL unless --fresh), so a part can be run by a
    # second runner without repeating its work
    todo = {} if a.rewrite else {arm: a.start for arm in a.arms if a.fresh or not any(r.get("closed") for r in hist[arm])}
    ver = "unknown"
    for arm in a.arms:                       # a rewrite keeps the version the passes were built with
        f = out / f"{arm}.json"
        if a.rewrite and f.exists():
            ver = json.loads(f.read_text())["tool"].replace("Vivado ", "")
    base = f"run{len(list((ROOT / 'build' / 'b92' / 'ooc' / PARTS[a.part]).glob('run*_pass1')))+1}"
    for p in range(a.passes):
        if not todo:
            break
        res, v = run_pass(a.part, sorted(todo.items()), f"{base}_pass{p + 1}", os.getpid())
        ver = v if v != "unknown" else ver
        nxt = {}
        for arm, r in res.items():
            hist[arm].append(r)
            if r["status"] != "ok":
                continue
            t = math.ceil((r["clock_ns"] - min(r["wns_ns"], 2 * (r["wpws_ns"] or 0.0))) * 20 - 1e-6) / 20
            if r["closed"]:
                fails = [x["clock_ns"] for x in hist[arm] if x.get("status") == "ok" and not x["closed"]]
                if t <= r["clock_ns"] - 0.05 and not any(f >= t for f in fails):
                    nxt[arm] = t
                continue
            closed = [x["clock_ns"] for x in hist[arm] if x.get("closed")]
            t = t + (0.05 if p >= 1 else 0.0)
            if not closed or t < min(closed):
                nxt[arm] = t
        todo = nxt
    for arm, h in hist.items():
        closed = [r for r in h if r.get("closed")]
        best = min(closed, key=lambda r: r["clock_ns"]) if closed else None
        if best:
            rd = out / "reports" / arm
            rd.mkdir(parents=True, exist_ok=True)
            for f in ("utilization.rpt", "timing_summary.rpt"):
                shutil.copy(Path(best["wd"]) / f, rd / f)
        src = sources(arm)
        rec = {"arm": arm, "part": a.part, "tool": f"Vivado {ver}", "flow": "out of context, post-route, one thread",
               "wrapper": "an input register for the features before the arm (87 ooc_wrap); the arm's own output register",
               "latency_clocks": int(re.search(r"localparam int LATENCY = (\d+);", Path(src[-1]).read_text()).group(1)),
               "closed_at_ns": best["clock_ns"] if best else None,
               "closed_at_mhz": round(1000 / best["clock_ns"], 1) if best else None,
               "at_closed_clock": {k: v for k, v in best.items() if k != "wd"} if best else None,
               "passes": [{k: v for k, v in r.items() if k != "wd"} | {"wd": r.get("wd")} for r in h]}
        (out / f"{arm}.json").write_text(json.dumps(rec, indent=1))
        print(arm, rec["closed_at_ns"], best and {k: best[k] for k in ("lut", "ff", "wns_ns", "wpws_ns")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
