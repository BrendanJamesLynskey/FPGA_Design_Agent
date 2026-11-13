#!/usr/bin/env python3
"""IP library entry -> CPU custom-instruction unit (brief 64A+).

An ip_lib entry that declares a `function_unit:` contract in its ip.yaml (two register operands, one result, no state,
an issue pulse and a done pulse a fixed number of clocks later) is wrapped into a unit with the port a simple in-order
pipeline uses for a multi-cycle execute unit (the same handshake as the BRV32P core's divider):

    start   a custom instruction for this unit is in EX        busy    hold EX (and the stages before it)
    hold    the pipeline is stalled: keep a finished result    valid   the result is on `result` this clock
    kill    the instruction in EX is flushed                   result  the value for rd
    funct3, funct7, a (rs1), b (rs2)

    python3 -m hwsw.cfu crc32_step --variant word --out build/cfu       # cfu_crc32_step.sv, cfu_ops.vh, cfu_crc32_step.h
    python3 -m hwsw.cfu --check                                          # every entry's contract against the rules

The generated C header wraps the instruction for GCC with the `.insn` directive (custom-2 opcode 0x5b by default), so
no compiler change is needed. The eligibility rules are those of the KB skill `custom-instruction-or-accelerator`
(hwsw/partition.py `DEFAULTS`): at most two source registers and one result, no state between calls, and a latency the
pipeline can afford to stall for (longer needs --allow-long, and is reported).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flow import ipvariants  # noqa: E402
from hwsw.partition import DEFAULTS  # noqa: E402

OPCODES = {"custom-0": 0x0B, "custom-1": 0x2B, "custom-2": 0x5B, "custom-3": 0x7B}
KEYS = {"operation", "summary", "operands", "result", "issue", "done", "state", "model"}


class CfuError(ValueError):
    pass


def contract(block: str) -> dict:
    y = yaml.safe_load((ipvariants.IP / block / "ip.yaml").read_text())
    fu = y.get("function_unit")
    if not fu:
        raise CfuError(f"{block}: no function_unit contract in ip.yaml")
    return {**fu, "top": y["top"], "rtl": [str(ipvariants.IP / block / f) for f in y["rtl"]],
            "variant_param": y.get("variant_param"), "variants": list((y.get("variants") or {}).keys())}


def check(block: str, variant: str | None = None, allow_long: bool = False) -> list[str]:
    """Why this entry (at this variant) cannot be a custom instruction as declared; [] = fine."""
    try:
        fu = contract(block)
    except CfuError as ex:
        return [str(ex)]
    e = []
    extra = set(fu) - KEYS - {"top", "rtl", "variant_param", "variants"}
    if extra:
        e.append(f"{block}: unknown function_unit keys {sorted(extra)}")
    for k in KEYS - {"summary", "model"}:
        if k not in fu:
            e.append(f"{block}: function_unit.{k} missing")
    ops = fu.get("operands") or {}
    if not set(ops) <= {"rs1", "rs2"} or not ops:
        e.append(f"{block}: operands must map rs1 and/or rs2 to ports (got {sorted(ops)}): "
                 f"at most {DEFAULTS['max_src_regs']} source registers")
    if set(fu.get("result") or {}) != {"rd"}:
        e.append(f"{block}: result must map rd (one destination register) to a port")
    if fu.get("state") not in ("none", None):
        e.append(f"{block}: state {fu.get('state')!r}: a custom instruction keeps no state between calls here "
                 "(small configuration state belongs in a custom CSR, which this generator does not make)")
    if not re.match(r"^[a-z][a-z0-9.]*$", str(fu.get("operation", ""))):
        e.append(f"{block}: operation {fu.get('operation')!r} must be a lower-case mnemonic")
    if fu.get("model") and not (ROOT / str(fu["model"]).split(":")[0]).exists():
        e.append(f"{block}: model {fu['model']} not found")
    vs = [variant] if variant else (fu["variants"] or [None])
    for v in vs:
        if fu["variants"] and v not in fu["variants"]:
            e.append(f"{block}: no variant {v!r} ({', '.join(fu['variants'])})")
            continue
        lat = latency(block, v)
        if lat < 1:
            e.append(f"{block}/{v}: latency {lat}: the unit must register its result (latency at least 1)")
        if lat > DEFAULTS["max_stall_clocks"] and not allow_long:
            e.append(f"{block}/{v}: latency {lat} clocks stalls the pipeline more than {DEFAULTS['max_stall_clocks']} "
                     "clocks per instruction (use a lower-latency variant, or --allow-long and say why)")
    rtl = "\n".join(Path(f).read_text() for f in fu["rtl"] if Path(f).exists())
    for p in [*(ops.values()), *(fu.get("result") or {}).values(), fu.get("issue"), fu.get("done")]:
        if p and not re.search(rf"\b{re.escape(str(p))}\b", rtl):
            e.append(f"{block}: port {p} of the contract is not in the RTL")
    return e


def latency(block: str, variant: str | None) -> int:
    if variant:
        return int(ipvariants.predict(block, variant, {})["latency"])
    y = yaml.safe_load((ipvariants.IP / block / "ip.yaml").read_text())
    return int(y["function_unit"].get("latency", 1))


def emit_sv(block: str, variant: str | None, funct3: int, funct7: int) -> str:
    fu = contract(block)
    lat = latency(block, variant)
    ops, res = fu["operands"], fu["result"]
    vp = fu["variant_param"]
    params = f' #(.{vp}("{variant}"))' if vp and variant else ""
    conn = [f".clk(clk)", f".rst(!rst_n)", f".{fu['issue']}(go)"]
    conn += [f".{port}({'a_in' if r == 'rs1' else 'b_in'})" for r, port in ops.items()]
    conn += [f".{fu['done']}(unit_valid)", f".{res['rd']}(unit_out)"]
    return f"""// Generated by hwsw/cfu.py from ip_lib/{block} ({variant or 'single implementation'}, latency {lat}); do not edit.
// {fu['operation']} rd, rs1, rs2: {fu.get('summary', '')}
// Custom-instruction port of a simple in-order pipeline (the BRV32P divider's handshake): the instruction waits in EX
// while busy is high; the result is on `result` when valid is high and is held while `hold` stalls the pipeline.
// The operands are taken on the instruction's first clock in EX and kept (a_q, b_q): a start delayed past that clock
// must not read the forwarding path, which by then may show a stale value. A killed operation is let finish inside
// the unit (inflight) and its result dropped; the next one waits for it.
// Simulation only: with CFU_MONITOR defined, each kill and each delayed start is printed (hwsw/cfu_core/run_bench.py).
// Decodes funct3 {funct3} and funct7 {funct7} only (cfu_ops.vh); the core's decoder marks other encodings illegal.
module cfu_{block} (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        start,
    input  logic        hold,
    input  logic        kill,
    input  logic [2:0]  funct3,
    input  logic [6:0]  funct7,
    input  logic [31:0] a,
    input  logic [31:0] b,
    output logic [31:0] result,
    output logic        busy,
    output logic        valid
);
    localparam int LATENCY = {lat};
    logic        active, have, inflight, unit_valid, go, done_now, held;
    logic [31:0] res_q, unit_out, a_q, b_q, a_in, b_in;
    assign go       = start && !active && !inflight && !kill;
    assign a_in     = held ? a_q : a;      // the first EX clock's operands, wherever the start lands
    assign b_in     = held ? b_q : b;
    assign done_now = active && (have || unit_valid);
    assign busy     = start && !done_now;
    assign valid    = done_now;
    assign result   = have ? res_q : unit_out;

`ifdef CFU_KEEP_UNIT
    (* keep_hierarchy = "yes" *)                  // an experiment: no logic moves across the unit's boundary
`endif
    {fu['top']}{params} u_unit ({', '.join(conn)});

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            active <= 1'b0;
            have <= 1'b0;
            inflight <= 1'b0;
            res_q <= 32'd0;
            held <= 1'b0;
            a_q <= 32'd0;
            b_q <= 32'd0;
        end else begin
            if (go) inflight <= 1'b1;
            else if (unit_valid) inflight <= 1'b0;
            if (kill || go) held <= 1'b0;                     // a start, or a new instruction next
            else if (start && !active && !held) begin         // first EX clock and the start must wait: keep them
                held <= 1'b1;
                a_q <= a;
                b_q <= b;
            end
            if (kill) begin
                active <= 1'b0;
                have <= 1'b0;
            end else if (go) begin
                active <= 1'b1;
                have <= 1'b0;
            end else if (active) begin
                if (unit_valid && !have) begin
                    have <= 1'b1;
                    res_q <= unit_out;
                end
                if (done_now && !hold) begin       // the pipeline takes the result this clock
                    active <= 1'b0;
                    have <= 1'b0;
                end
            end
        end
    end

    logic unused_ok;
    assign unused_ok = ^{{funct3, funct7}};

`ifdef CFU_MONITOR
    always @(posedge clk) if (rst_n) begin
        if (kill && start)
            $display("CFU_MONITOR kill t=%0t active=%0d inflight=%0d have=%0d unit_valid=%0d", $time, active, inflight,
                     have, unit_valid);
        if (start && !active && inflight && !kill)
            $display("CFU_MONITOR wait t=%0t held=%0d", $time, held);
    end
`endif
endmodule
"""


def emit_vh(block: str, funct3: int, funct7: int) -> str:
    return (f"// Generated by hwsw/cfu.py for ip_lib/{block}; do not edit. The unit's module name, and the encodings the core's\n"
            "// decoder accepts on the custom opcode the unit is wired to (any other is an illegal instruction).\n"
            "`ifndef CFU_OPS_VH\n`define CFU_OPS_VH\n"
            f"`define CFU_MODULE cfu_{block}\n"
            f"`define CFU_LEGAL(f3, f7) ((f3) == 3'd{funct3} && (f7) == 7'd{funct7})\n"
            "`endif\n")


def emit_h(block: str, variant: str | None, funct3: int, funct7: int, opcode: int) -> str:
    fu = contract(block)
    name = fu["operation"].replace(".", "_")
    return f"""/* Generated by hwsw/cfu.py from ip_lib/{block} ({variant or 'single implementation'}); do not edit.
 * {fu['operation']} rd, rs1, rs2: {fu.get('summary', '')}
 * Encoded with the GNU assembler's .insn directive: R-type, opcode 0x{opcode:02x}, funct3 {funct3}, funct7 {funct7}. */
#ifndef CFU_{block.upper()}_H
#define CFU_{block.upper()}_H
#include <stdint.h>

static inline uint32_t {name}(uint32_t rs1, uint32_t rs2)
{{
    uint32_t rd;
    __asm__ (".insn r 0x{opcode:02x}, {funct3}, {funct7}, %0, %1, %2" : "=r" (rd) : "r" (rs1), "r" (rs2));
    return rd;
}}

#endif
"""


def generate(block: str, variant: str | None, out: Path, funct3: int = 0, funct7: int = 0, opcode: str = "custom-2",
             allow_long: bool = False) -> dict[str, Path]:
    errs = check(block, variant, allow_long)
    if errs:
        raise CfuError("; ".join(errs))
    out.mkdir(parents=True, exist_ok=True)
    files = {"sv": out / f"cfu_{block}.sv", "vh": out / "cfu_ops.vh", "h": out / f"cfu_{block}.h"}
    files["sv"].write_text(emit_sv(block, variant, funct3, funct7))
    files["vh"].write_text(emit_vh(block, funct3, funct7))
    files["h"].write_text(emit_h(block, variant, funct3, funct7, OPCODES[opcode]))
    return files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m hwsw.cfu", description=__doc__.split("\n\n")[0])
    ap.add_argument("block", nargs="?")
    ap.add_argument("--variant", default=None)
    ap.add_argument("--out", default="build/cfu")
    ap.add_argument("--funct3", type=int, default=0)
    ap.add_argument("--funct7", type=int, default=0)
    ap.add_argument("--opcode", default="custom-2", choices=sorted(OPCODES))
    ap.add_argument("--allow-long", action="store_true", help="accept a latency above the stall limit")
    ap.add_argument("--check", action="store_true", help="check every ip_lib entry that declares a function_unit")
    a = ap.parse_args(argv)
    if a.check:
        blocks = [b for b in ipvariants.entries() if (yaml.safe_load((ipvariants.IP / b / "ip.yaml").read_text())
                                                      or {}).get("function_unit")]
        errs = [x for b in blocks for x in check(b, None, allow_long=True)]
        for x in errs:
            print(x)
        print(f"{len(blocks)} entries with a function_unit contract, {len(errs)} problems")
        return 1 if errs else 0
    if not a.block:
        ap.error("give a block, or --check")
    try:
        for k, p in generate(a.block, a.variant, Path(a.out), a.funct3, a.funct7, a.opcode, a.allow_long).items():
            print(p)
    except CfuError as ex:
        print(f"cfu: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
