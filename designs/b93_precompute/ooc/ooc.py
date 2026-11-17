#!/usr/bin/env python3
"""Post-route, out-of-context cost and clock of each brief 93 subject on a part, Vivado 2026.1, by the brief 87/89
method (one thread, a memory-capped scope, clock search until setup, hold and pulse width all pass). Subjects:

    gbt_comb lg_small_comb      the 87 trees and 89 network as they are (arm 1 blocks)
    gbt_pe gbt_pe2 lgs_pe lgs_pe2   the partial-evaluation blocks, table fill 1 or 2 clocks (arm 3 blocks)
    ml_feat ml_feat_pre         the feature unit at the price field (87) and early (93) (arm 1 / arm 2 front ends)

    python3 -m designs.b93_precompute.ooc.ooc --part xck26-sfvc784-2LV-c --arms gbt_comb gbt_pe [--start 4.0]

Wrappers: input registers on every input of the subject (the producer's registers) and, for the front ends, output
registers; the wrappers' own flip-flops are counted in the FF column (the wrapper FF count is recorded per subject).
For the partial-evaluation blocks the worst early path (e_f/e_v registers to anything) and the worst late path (l_x/l_v
registers to anything) are reported separately. Results: results/b93/ooc/<part>/<subject>.json.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from designs.b87_ml_trading.ooc.ooc import WRAP, parse  # noqa: E402
from designs.b89_lutnet_gen.ooc.ooc import fix_util  # noqa: E402
from flow.ipchar import tcl_list, vivado  # noqa: E402

D = Path(__file__).resolve().parents[1]
TCL = D / "ooc" / "ooc.tcl"
PARTS = {"xck26-sfvc784-2LV-c": "k26", "xc7a100tcsg324-1": "a7"}
B87 = ROOT / "designs" / "b87_ml_trading" / "rtl"
B89 = ROOT / "designs" / "b89_lutnet_gen" / "rtl" / "gen"
G87 = B87 / "gen"
G93 = D / "rtl" / "gen"

PE_WRAP = """// ooc_wrap for {arm}: input registers for the early features and the late value, then the block.
module ooc_wrap (input logic clk, input logic rst, input logic e_v, input logic [37:0] e_f, input logic l_v,
                 input logic [7:0] l_x, output logic out_v, output logic [1:0] out_cls);
    logic ev_q, lv_q;
    logic [37:0] e_q;
    logic [7:0] l_q;
    always_ff @(posedge clk) begin
        e_q <= e_f; ev_q <= e_v; l_q <= l_x; lv_q <= l_v;
    end
    {arm} u_arm (.clk, .rst, .e_v(ev_q), .e_f(e_q), .l_v(lv_q), .l_x(l_q), .out_v, .out_cls);
endmodule
"""
FEAT_WRAP = """// ooc_wrap for {arm}: every input registered (the producers' registers), the feature vector registered at the output.
module ooc_wrap (input logic clk, input logic rst, input logic [15:0] ml_inst, input logic inst_v, input logic msg_px_v,
                 input logic [7:0] msg_type, input logic msg_side, input logic [15:0] msg_inst, input logic bk_valid,
                 input logic [31:0] bk_bid_px, bk_bid_sz, bk_ask_px, bk_ask_sz,
                 output logic feat_v, output logic [37:0] feat);
    logic [15:0] mi_q, ms_q; logic iv_q, pv_q, side_q, bv_q; logic [7:0] ty_q;
    logic [31:0] bp_q, bs_q, ap_q, as_q;
    always_ff @(posedge clk) begin
        mi_q <= ml_inst; ms_q <= msg_inst; iv_q <= inst_v; pv_q <= msg_px_v; ty_q <= msg_type; side_q <= msg_side;
        bv_q <= bk_valid; bp_q <= bk_bid_px; bs_q <= bk_bid_sz; ap_q <= bk_ask_px; as_q <= bk_ask_sz;
    end
    logic fv; logic [37:0] f; logic tv;
    {inst} u_f (.clk, .rst, .ml_inst(mi_q), {instport}.msg_px_v(pv_q), .msg_type(ty_q), .msg_side(side_q), .msg_inst(ms_q),
                .bk_valid(bv_q), .bk_bid_px(bp_q), .bk_bid_sz(bs_q), .bk_ask_px(ap_q), .bk_ask_sz(as_q), {trk}.feat_v(fv), .feat(f));
    always_ff @(posedge clk) begin feat_v <= fv; feat <= f; end
endmodule
"""
PE_EXTRA = ("report_timing -from [get_cells -hier -filter {NAME =~ *e_q_reg* || NAME =~ *ev_q_reg*}] -max_paths 1 "
            "-file $wd/early_path.rpt; report_timing -from [get_cells -hier -filter {NAME =~ *l_q_reg* || NAME =~ *lv_q_reg*}] "
            "-max_paths 1 -file $wd/late_path.rpt")
# wrapper flip-flops (for the record): comb 39; PE 48; front ends 210 / 211, outputs included
SUBJECTS = {
    "gbt_comb": (WRAP, [G87 / "gbt_comb.sv"], "", 39),
    "lg_small_comb": (WRAP, [B89 / "lg_small_comb.sv"], "", 39),
    "gbt_pe": (PE_WRAP, [G93 / "gbt_pe.sv"], PE_EXTRA, 48),
    "gbt_pe2": (PE_WRAP, [G93 / "gbt_pe2.sv"], PE_EXTRA, 48),
    "lgs_pe": (PE_WRAP, [G93 / "lgs_pe.sv"], PE_EXTRA, 48),
    "lgs_pe2": (PE_WRAP, [G93 / "lgs_pe2.sv"], PE_EXTRA, 48),
    "ml_feat": (FEAT_WRAP, [B87 / "ml_feat.sv"], "", 210),
    "ml_feat_pre": (FEAT_WRAP, [D / "rtl" / "ml_feat_pre.sv"], "", 211),
}


def wrapper(arm: str) -> str:
    w = SUBJECTS[arm][0]
    if w is FEAT_WRAP:
        pre = arm == "ml_feat_pre"
        return w.format(arm=arm, inst=arm, instport=".inst_v(iv_q), " if pre else "", trk=".trk_v(tv), " if pre else "")
    return w.format(arm=arm)


def run_pass(part, jobs, tag, root):
    batch = ROOT / "build" / "b93" / "ooc" / PARTS[part] / tag
    batch.mkdir(parents=True, exist_ok=True)
    lines = [f"set ooc(part) {part}", "set ooc(jobs) {}"]
    wds = {}
    for arm, ck in jobs:
        wd = batch / f"{arm}_{ck:.2f}"
        wd.mkdir(parents=True, exist_ok=True)
        (wd / "ooc_wrap.sv").write_text(wrapper(arm))
        for mk in ("done.txt", "error.txt"):
            (wd / mk).unlink(missing_ok=True)
        lines.append("lappend ooc(jobs) " + tcl_list([arm, "ooc_wrap", str(wd), ck,
                                                       [str(p) for p in SUBJECTS[arm][1]] + [str(wd / "ooc_wrap.sv")],
                                                       SUBJECTS[arm][2]]))
        wds[arm] = (wd, ck)
    (batch / "jobs.tcl").write_text("\n".join(lines) + "\n")
    unit = f"b93-ooc-{root}-{PARTS[part]}-{tag}"
    cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", "MemoryMax=6G", "nice", "-n", "15",
           vivado(), "-mode", "batch", "-nojournal", "-log", str(batch / "vivado.log"), "-source", str(TCL),
           "-tclargs", str(batch / "jobs.tcl")]
    print(f"ooc: {part} pass {tag}: {len(jobs)} jobs, scope {unit}", flush=True)
    subprocess.run(cmd, cwd=batch)
    m = re.search(r"Vivado v(\S+) \(64-bit\)", (batch / "vivado.log").read_text()) if (batch / "vivado.log").exists() else None
    out = {}
    for arm, (wd, ck) in wds.items():
        r = fix_util(dict(parse(wd, ck), wd=str(wd)))
        for nm in ("early", "late"):
            f = wd / f"{nm}_path.rpt"
            if f.exists():
                mm = re.search(r"Slack \((?:MET|VIOLATED)\)\s*:\s*(-?\d+\.\d+)ns", f.read_text())
                if mm:
                    r[f"{nm}_path_slack_ns"] = float(mm.group(1))
                    r[f"{nm}_path_delay_ns"] = round(ck - float(mm.group(1)), 3)
        out[arm] = r
    return out, (m.group(1) if m else "unknown")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", required=True, choices=sorted(PARTS))
    ap.add_argument("--arms", nargs="+", required=True, choices=sorted(SUBJECTS))
    ap.add_argument("--start", type=float, default=4.0)
    ap.add_argument("--passes", type=int, default=4)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--tag", default="run")
    a = ap.parse_args(argv)
    out = ROOT / "results" / "b93" / "ooc" / PARTS[a.part]
    out.mkdir(parents=True, exist_ok=True)
    hist = {arm: [] for arm in a.arms}
    for arm in a.arms:
        f = out / f"{arm}.json"
        if f.exists() and not a.fresh:
            hist[arm] = json.loads(f.read_text())["passes"]
    todo = {arm: a.start for arm in a.arms if a.fresh or not any(r.get("closed") for r in hist[arm])}
    ver = "unknown"
    n = len(list((ROOT / "build" / "b93" / "ooc" / PARTS[a.part]).glob("*_pass1"))) + 1 if (ROOT / "build" / "b93" / "ooc" / PARTS[a.part]).exists() else 1
    base = f"{a.tag}{n}"
    for p in range(a.passes):
        if not todo:
            break
        res, v = run_pass(a.part, sorted(todo.items()), f"{base}_pass{p + 1}", a.tag)
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
        if best and Path(best["wd"]).exists():
            rd = out / "reports" / arm
            rd.mkdir(parents=True, exist_ok=True)
            for f in ("utilization.rpt", "timing_summary.rpt", "early_path.rpt", "late_path.rpt"):
                if (Path(best["wd"]) / f).exists():
                    shutil.copy(Path(best["wd"]) / f, rd / f)
        old = json.loads((out / f"{arm}.json").read_text())["tool"] if (out / f"{arm}.json").exists() else None
        rec = {"arm": arm, "part": a.part, "tool": f"Vivado {ver}" if ver != "unknown" else old,
               "flow": "out of context, post-route, one thread",
               "wrapper": "input registers before the subject (the producers' registers); front ends also register the outputs",
               "wrapper_flip_flops": SUBJECTS[arm][3],
               "closed_at_ns": best["clock_ns"] if best else None,
               "closed_at_mhz": round(1000 / best["clock_ns"], 1) if best else None,
               "at_closed_clock": {k: v for k, v in best.items() if k != "wd"} if best else None,
               "passes": h}
        (out / f"{arm}.json").write_text(json.dumps(rec, indent=1))
        print(arm, rec["closed_at_ns"], best and {k: best.get(k) for k in ("lut", "ff", "wns_ns", "wpws_ns", "early_path_delay_ns", "late_path_delay_ns")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
