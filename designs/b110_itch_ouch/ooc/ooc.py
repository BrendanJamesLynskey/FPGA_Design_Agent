#!/usr/bin/env python3
"""Post-route, out-of-context cost and clock of itch_ouch_top on the K26 (xck26-sfvc784-2LV-c), Vivado 2026.1 (brief 110).

    python3 -m designs.b110_itch_ouch.ooc.ooc [--clocks 6.2061 5.0 4.4] [--dry-run] [--tag NAME] [--param N_INST=4 ...]

The required clock is 6.2061 ns (161.1328125 MHz, the 10G core's user clock). Each clock is one job in one Vivado batch session (a memory-capped
scope, MemoryMax=6G, one thread, nice 15); take a heavy slot first (`_handoff/take_heavy_slot.sh`). The wrapper `ooc_wrap` registers every input
(the stream and the static configuration, as a register file and the MAC would); outputs are left as ports. Results: results/b110/ooc/<tag>.json
(each clock's LUT, FF, LUTRAM, block RAM, DSP, WNS, WHS, pulse-width slack, and the core's share by hierarchy), run directories build/b110/ooc/.
`closed_at_ns` is the smallest tried clock that closed (setup, hold and pulse width): a closed point, not a bound.
"""
from __future__ import annotations

import argparse
import json
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
REQUIRED_NS = 6.2061
BUILD = ROOT / "build" / "b110" / "ooc"
OUT = ROOT / "results" / "b110" / "ooc"
FILES = ["itch_pkg.sv", "mold_rx.sv", "itch_dec.sv", "book_core.sv", "ouch_enter.sv", "risk_glue.sv", "itch_ouch_top.sv"]


def wrap_text(n_inst: int, notional: int = 0) -> str:
    return f"""// ooc_wrap: registers on every input of itch_ouch_top (the payload stream from the MAC side, the configuration from a register file).
module ooc_wrap import itch_pkg::*; (
    input  logic clk, input logic rst,
    input  logic s_v_i, input logic [63:0] s_d_i, input logic s_sof_i, input logic s_eof_i, input logic [7:0] s_keep_i, input logic s_err_i,
    input  logic [{n_inst}*64-1:0] cfg_watch_i,
    input  logic [31:0] cfg_thr_i, cfg_qty_i, cfg_max_qty_i, cfg_max_pos_i, cfg_band_i, cfg_px_off_i, cfg_minqty_i,
    input  logic [7:0] cfg_tif_i, cfg_display_i, cfg_capacity_i, cfg_ise_i, cfg_cross_i, cfg_custtype_i,
    input  logic cfg_arm_i, cfg_kill_i, cfg_halt_on_gap_i, cfg_spec_i,
    input  logic [15:0] cfg_holdoff_i, input logic cfg_ref_sw_i, input logic [31:0] cfg_ref_px_i, cfg_ref_age_i, input logic ref_load_i,
    input  logic [63:0] cfg_max_notional_i, input logic [4:0] cfg_nt_shift_i, input logic [16*32-1:0] cfg_nt_tbl_i,
    input  logic clr_cnt_i, clr_flags_i, clr_book_i, clr_pos_i, clr_ref_i,
    output logic o_v, output logic [63:0] o_d, output logic o_sof, output logic o_eof, output logic [7:0] o_keep, output logic o_abort,
    output logic tu_v, output logic [15:0] flags, output logic [NC*32-1:0] cnt
);
    logic s_v, s_sof, s_eof, s_err, cfg_arm, cfg_kill, cfg_halt_on_gap, cfg_spec, clr_cnt, clr_flags, clr_book, clr_pos, clr_ref;
    logic [63:0] s_d; logic [7:0] s_keep;
    logic [{n_inst}*64-1:0] cfg_watch;
    logic [31:0] cfg_thr, cfg_qty, cfg_max_qty, cfg_max_pos, cfg_band, cfg_px_off, cfg_minqty;
    logic [15:0] cfg_holdoff; logic cfg_ref_sw, ref_load; logic [31:0] cfg_ref_px, cfg_ref_age; logic [63:0] cfg_max_notional; logic [4:0] cfg_nt_shift; logic [16*32-1:0] cfg_nt_tbl;
    logic [7:0] cfg_tif, cfg_display, cfg_capacity, cfg_ise, cfg_cross, cfg_custtype;
    always_ff @(posedge clk) begin
        s_v <= s_v_i; s_d <= s_d_i; s_sof <= s_sof_i; s_eof <= s_eof_i; s_keep <= s_keep_i; s_err <= s_err_i;
        cfg_watch <= cfg_watch_i; cfg_thr <= cfg_thr_i; cfg_qty <= cfg_qty_i; cfg_max_qty <= cfg_max_qty_i; cfg_max_pos <= cfg_max_pos_i;
        cfg_band <= cfg_band_i; cfg_px_off <= cfg_px_off_i; cfg_minqty <= cfg_minqty_i; cfg_tif <= cfg_tif_i; cfg_display <= cfg_display_i;
        cfg_capacity <= cfg_capacity_i; cfg_ise <= cfg_ise_i; cfg_cross <= cfg_cross_i; cfg_custtype <= cfg_custtype_i;
        cfg_arm <= cfg_arm_i; cfg_kill <= cfg_kill_i; cfg_halt_on_gap <= cfg_halt_on_gap_i; cfg_spec <= cfg_spec_i;
        cfg_holdoff <= cfg_holdoff_i; cfg_ref_sw <= cfg_ref_sw_i; cfg_ref_px <= cfg_ref_px_i; cfg_ref_age <= cfg_ref_age_i; ref_load <= ref_load_i;
        cfg_max_notional <= cfg_max_notional_i; cfg_nt_shift <= cfg_nt_shift_i; cfg_nt_tbl <= cfg_nt_tbl_i;
        clr_cnt <= clr_cnt_i; clr_flags <= clr_flags_i; clr_book <= clr_book_i; clr_pos <= clr_pos_i; clr_ref <= clr_ref_i;
    end
    itch_ouch_top #(.N_INST({n_inst}), .NOTIONAL_MODE({notional})) u_dut (.clk, .rst, .s_v, .s_d, .s_sof, .s_eof, .s_keep, .s_err, .cfg_watch, .cfg_thr, .cfg_qty, .cfg_max_qty,
        .cfg_max_pos, .cfg_band, .cfg_px_off, .cfg_minqty, .cfg_tif, .cfg_display, .cfg_capacity, .cfg_ise, .cfg_cross, .cfg_custtype, .cfg_arm, .cfg_kill,
        .cfg_halt_on_gap, .cfg_spec, .cfg_holdoff, .cfg_ref_sw, .cfg_ref_px, .cfg_ref_age, .ref_load, .cfg_max_notional, .cfg_nt_shift, .cfg_nt_tbl, .clr_cnt, .clr_flags, .clr_book, .clr_pos, .clr_ref, .o_v, .o_d, .o_sof, .o_eof, .o_keep, .o_abort,
        .m_v(), .m_len(), .e_v(), .e_k(), .tu_v, .tu_inst(), .tu_side(), .tu_px(), .tu_sz(), .tu_ok(), .tob_px(), .tob_sz(), .tob_ok(), .flags, .sys_code(), .cnt);
endmodule
"""


def parse(wd: Path, clock_ns: float) -> dict:
    if (wd / "error.txt").exists():
        return {"status": "error: " + (wd / "error.txt").read_text().strip()[:300], "clock_ns": clock_ns}
    if not (wd / "done.txt").exists():
        return {"status": "not run", "clock_ns": clock_ns}
    u = (wd / "utilization.rpt").read_text()
    t = (wd / "timing_summary.rpt").read_text()
    m = re.search(r"WNS\(ns\)\s+TNS\(ns\).*?\n\s*-+.*?\n\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+\d+\s+\d+\s+(-?\d+\.\d+)", t, re.S)
    r = {"status": "ok", "clock_ns": clock_ns,
         "lut": _row(u, "CLB LUTs"), "lut_as_logic": _row(u, "LUT as Logic"), "lut_as_memory": _row(u, "LUT as Memory"), "ff": _row(u, "CLB Registers"),
         "carry8": _row(u, "CARRY8"), "dsp": _row(u, "DSPs"), "bram_tiles": _row(u, "Block RAM Tile"),
         "wns_ns": float(m.group(1)) if m else None, "whs_ns": float(m.group(3)) if m else None, "wpws_ns": float(m.group(5)) if m else None,
         "build_seconds": int((wd / "done.txt").read_text().strip())}
    r["closed"] = r["wns_ns"] is not None and r["wns_ns"] >= 0 and r["whs_ns"] >= 0 and r["wpws_ns"] >= 0
    h = wd / "utilization_hier.rpt"
    if h.is_file():
        blocks = {}
        for line in h.read_text().splitlines():
            c = [x.strip() for x in line.split("|")]
            if len(c) > 11 and c[1] and not c[1].startswith("(") and c[3].isdigit() and c[1] not in ("Instance", "ooc_wrap"):
                blocks[c[1]] = {"module": c[2], "lut": int(c[3]), "logic_lut": int(c[4]), "lutram": int(c[5]), "ff": int(c[7]), "bram36": int(c[8]), "bram18": int(c[9]), "dsp": int(c[11])}
        r["blocks"] = blocks
        if "u_dut" in blocks:
            r["core_lut"], r["core_lutram"], r["core_ff"] = blocks["u_dut"]["lut"], blocks["u_dut"]["lutram"], blocks["u_dut"]["ff"]
    return r


def run(jobs: list[tuple[float, Path]], tag: str, n_inst: int, generics: dict, dry: bool) -> dict:
    batch = BUILD / tag
    batch.mkdir(parents=True, exist_ok=True)
    wrap = batch / "ooc_wrap.sv"
    wrap.write_text(wrap_text(n_inst, int(generics.get("NOTIONAL_MODE", 0))))
    srcs = [str(D / "rtl" / f) for f in FILES] + [str(wrap)]
    lines = [f"set ooc(part) {PART}", "set ooc(top) ooc_wrap", "set ooc(jobs) {}"]
    wds = {}
    for ck, wd in jobs:
        wd.mkdir(parents=True, exist_ok=True)
        for mk in ("done.txt", "error.txt"):
            (wd / mk).unlink(missing_ok=True)
        lines.append("lappend ooc(jobs) " + tcl_list([f"c{ck}", str(wd), ck, srcs, [x for kv in generics.items() for x in kv]]))
        wds[ck] = wd
    (batch / "jobs.tcl").write_text("\n".join(lines) + "\n")
    if dry:
        print((batch / "jobs.tcl").read_text())
        return {}
    unit = f"b110-ooc-{os.getpid()}"
    cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", "MemoryMax=6G", "nice", "-n", "15",
           vivado(), "-mode", "batch", "-nojournal", "-log", str(batch / "vivado.log"), "-source", str(D / "ooc" / "ooc.tcl"), "-tclargs", str(batch / "jobs.tcl")]
    print(f"ooc: {len(jobs)} jobs, scope {unit}", flush=True)
    subprocess.run(cmd, cwd=batch)
    return {ck: parse(wd, ck) for ck, wd in wds.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clocks", nargs="*", type=float, default=[REQUIRED_NS, 5.0, 4.4])
    ap.add_argument("--tag", default="itch_ouch_top")
    ap.add_argument("--param", nargs="*", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--parse-only", action="store_true", help="rebuild the JSON from the reports of an earlier run (no Vivado)")
    a = ap.parse_args(argv)
    generics = dict(p.split("=") for p in a.param)
    n_inst = int(generics.get("N_INST", 4))
    batch = BUILD / a.tag
    if a.parse_only:
        res = {c: parse(batch / f"c{c}", c) for c in a.clocks}
    else:
        res = run([(c, batch / f"c{c}") for c in a.clocks], a.tag, n_inst, generics, a.dry_run)
    if a.dry_run:
        return 0
    runs = [res[c] for c in a.clocks]
    ok = [r for r in runs if r.get("closed")]
    at_req = next((r for r in runs if abs(r["clock_ns"] - REQUIRED_NS) < 1e-9), None)
    out = {"design": "itch_ouch_top", "part": PART, "vivado": "2026.1", "parameters": generics or {"N_INST": 4, "LEVELS": 8, "ORD_AW": 8},
           "required_clock_ns": REQUIRED_NS, "required_clock_mhz": round(1000.0 / REQUIRED_NS, 3), "required_closed": bool(at_req and at_req.get("closed")), "at_required": at_req,
           "closed_at_ns": min((r["clock_ns"] for r in ok), default=None), "runs": runs,
           "note": "out of context: no clock buffer, no I/O, no jitter; inputs registered in ooc_wrap; one thread; closed means setup, hold and pulse width met"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.tag}.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("required_closed", "closed_at_ns")}), [(r["clock_ns"], r.get("wns_ns"), r.get("lut")) for r in runs])
    return 0


if __name__ == "__main__":
    sys.exit(main())
