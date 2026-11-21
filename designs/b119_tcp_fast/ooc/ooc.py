#!/usr/bin/env python3
"""Post-route, out-of-context cost and clock of tcp_fast on the K26 (xck26-sfvc784-2LV-c), Vivado 2026.1 (brief 119).

    python3 -m designs.b119_tcp_fast.ooc.ooc [--clocks 6.2061 5.0 4.4] [--dry-run] [--tag NAME] []

The required clock is 6.2061 ns (161.1328125 MHz, the 10G core's user clock). Each clock is one job in one Vivado batch session (a memory-capped
scope, MemoryMax=6G, one thread, nice 15); take a heavy slot first (`_handoff/take_heavy_slot.sh`). The wrapper `ooc_wrap` registers every input
(the stream and the static configuration, as a register file and the MAC would); outputs are left as ports. Results: results/b119/ooc/<tag>.json
(each clock's LUT, FF, LUTRAM, block RAM, DSP, WNS, WHS, pulse-width slack, and the core's share by hierarchy), run directories build/b119/ooc/.
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
BUILD = ROOT / "build" / "b119" / "ooc"
OUT = ROOT / "results" / "b119" / "ooc"
OUCH_ENTER = ROOT / "designs" / "b110_itch_ouch" / "rtl" / "ouch_enter.sv"          # brief 110's frame builder, used inside tcp_fast
FILES = [OUCH_ENTER, D / "rtl" / "tcp_fast.sv"]


def wrap_text() -> str:
    return """// ooc_wrap: registers on every input of tcp_fast (the order side from risk_glue's registers, the configuration and the software bus from a register file).
module ooc_wrap (
    input  logic clk, input logic rst,
    input  logic go_i, input logic go_spec_i, input logic [63:0] f_sym_i, input logic [31:0] f_px_i, f_qty_i, f_ref_i, input logic commit_i, input logic abort_i,
    input  logic [7:0] cfg_tif_i, cfg_display_i, cfg_capacity_i, cfg_ise_i, cfg_cross_i, cfg_custtype_i, input logic [31:0] cfg_minqty_i,
    input  logic sw_we_i, input logic [4:0] sw_waddr_i, input logic [31:0] sw_wdata_i, input logic [4:0] sw_raddr_i,
    output logic busy, output logic late, output logic refuse_v, output logic [2:0] refuse_code,
    output logic o_v, output logic [63:0] o_d, output logic o_sof, output logic o_eof, output logic [7:0] o_keep, output logic o_poison,
    output logic rec_v, output logic [31:0] rec_seq, output logic [15:0] rec_len, output logic [15:0] rec_id, output logic [511:0] rec_pay,
    output logic [31:0] sw_rdata
);
    logic go, go_spec, commit, abort, sw_we;
    logic [63:0] f_sym; logic [31:0] f_px, f_qty, f_ref, cfg_minqty, sw_wdata; logic [7:0] cfg_tif, cfg_display, cfg_capacity, cfg_ise, cfg_cross, cfg_custtype;
    logic [4:0] sw_waddr, sw_raddr;
    always_ff @(posedge clk) begin
        go <= go_i; go_spec <= go_spec_i; f_sym <= f_sym_i; f_px <= f_px_i; f_qty <= f_qty_i; f_ref <= f_ref_i; commit <= commit_i; abort <= abort_i;
        cfg_tif <= cfg_tif_i; cfg_display <= cfg_display_i; cfg_capacity <= cfg_capacity_i; cfg_ise <= cfg_ise_i; cfg_cross <= cfg_cross_i;
        cfg_custtype <= cfg_custtype_i; cfg_minqty <= cfg_minqty_i; sw_we <= sw_we_i; sw_waddr <= sw_waddr_i; sw_wdata <= sw_wdata_i; sw_raddr <= sw_raddr_i;
    end
    tcp_fast u_dut (.clk, .rst, .go, .go_spec, .f_sym, .f_px, .f_qty, .f_ref, .commit, .abort, .cfg_tif, .cfg_display, .cfg_capacity, .cfg_ise, .cfg_cross,
        .cfg_custtype, .cfg_minqty, .busy, .late, .refuse_v, .refuse_code, .o_v, .o_d, .o_sof, .o_eof, .o_keep, .o_poison,
        .rec_v, .rec_seq, .rec_len, .rec_id, .rec_pay, .sw_we, .sw_waddr, .sw_wdata, .sw_raddr, .sw_rdata);
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


def run(jobs: list[tuple[float, Path]], tag: str, generics: dict, dry: bool) -> dict:
    batch = BUILD / tag
    batch.mkdir(parents=True, exist_ok=True)
    wrap = batch / "ooc_wrap.sv"
    wrap.write_text(wrap_text())
    srcs = [str(f) for f in FILES] + [str(wrap)]
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
    unit = f"b119-ooc-{os.getpid()}"
    cmd = ["systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "-p", "MemoryMax=6G", "nice", "-n", "15",
           vivado(), "-mode", "batch", "-nojournal", "-log", str(batch / "vivado.log"), "-source", str(D / "ooc" / "ooc.tcl"), "-tclargs", str(batch / "jobs.tcl")]
    print(f"ooc: {len(jobs)} jobs, scope {unit}", flush=True)
    subprocess.run(cmd, cwd=batch)
    return {ck: parse(wd, ck) for ck, wd in wds.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clocks", nargs="*", type=float, default=[REQUIRED_NS, 5.0, 4.4])
    ap.add_argument("--tag", default="tcp_fast")
    ap.add_argument("--param", nargs="*", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--parse-only", action="store_true", help="rebuild the JSON from the reports of an earlier run (no Vivado)")
    a = ap.parse_args(argv)
    generics = dict(p.split("=") for p in a.param)
    batch = BUILD / a.tag
    if a.parse_only:
        res = {c: parse(batch / f"c{c}", c) for c in a.clocks}
    else:
        res = run([(c, batch / f"c{c}") for c in a.clocks], a.tag, generics, a.dry_run)
    if a.dry_run:
        return 0
    runs = [res[c] for c in a.clocks]
    ok = [r for r in runs if r.get("closed")]
    at_req = next((r for r in runs if abs(r["clock_ns"] - REQUIRED_NS) < 1e-9), None)
    out = {"design": "tcp_fast", "part": PART, "vivado": "2026.1", "parameters": generics or {},
           "required_clock_ns": REQUIRED_NS, "required_clock_mhz": round(1000.0 / REQUIRED_NS, 3), "required_closed": bool(at_req and at_req.get("closed")), "at_required": at_req,
           "closed_at_ns": min((r["clock_ns"] for r in ok), default=None), "runs": runs,
           "note": "out of context: no clock buffer, no I/O, no jitter; inputs registered in ooc_wrap; one thread; closed means setup, hold and pulse width met"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{a.tag}.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("required_closed", "closed_at_ns")}), [(r["clock_ns"], r.get("wns_ns"), r.get("lut")) for r in runs])
    return 0


if __name__ == "__main__":
    sys.exit(main())
