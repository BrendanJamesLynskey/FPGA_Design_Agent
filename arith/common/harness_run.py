"""Packaged verification harness runner (brief 139b, owner decision 24): rerun the library's bench against YOUR instance of a function.

The instance must have the library's packed stream interface (the same ports as <function>_sel.sv: clk, rst, in_valid, in_ready, in_data,
out_valid, out_data), and may be any module name and any parameter names. The runner builds the vectors from the function's model, drives them
with input gaps, checks every output value, the order and the measured latency of every result, and reports coverage of the target bins in
harness/coverage.yaml. Exit status 0 only if everything passed and every coverage bin was hit.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import yaml

from arith.common import sim

PORT_LIST = ".clk(clk), .rst(rst), .in_valid(in_valid), .in_ready(in_ready), .in_data(in_data), .out_valid(out_valid), .out_data(out_data)"


def tb_text(dut: str, params: dict[str, int]) -> str:
    p = ", ".join(f".{k}({v})" for k, v in params.items())
    return f"""`timescale 1ns/1ps
module tb_user #(parameter int IN_W = 8, parameter int OUT_W = 8, parameter int NVEC = 16, parameter int LAT = 1, parameter int GAP_PCT = 0, parameter int SEED = 1);
    logic clk, rst, in_valid, in_ready, out_valid;
    logic [IN_W-1:0] in_data;
    logic [OUT_W-1:0] out_data;
    tb_stream #(.IN_W(IN_W), .OUT_W(OUT_W), .NVEC(NVEC), .LAT(LAT), .GAP_PCT(GAP_PCT), .SEED(SEED)) h (.clk, .rst, .in_valid, .in_ready, .in_data, .out_valid, .out_data);
    {dut} #({p}) dut ({PORT_LIST});
endmodule
"""


def coverage(fn_dir: Path, vin: list[int], decode) -> dict:
    cov = yaml.safe_load((fn_dir / "harness" / "coverage.yaml").read_text())["bins"]
    rows = decode(vin)
    out = {}
    for name, expr in cov.items():
        out[name] = sum(1 for r in rows if eval(expr, {"__builtins__": {}}, r))
    return out


def main(fn_dir: Path, plan, decode, argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dut", required=True, help="module name of your instance")
    ap.add_argument("--rtl", nargs="+", required=True, help="your RTL files")
    ap.add_argument("--param", action="append", default=[], help="NAME=VALUE parameter of your instance (also the function parameters the model needs)")
    ap.add_argument("--latency", type=int, default=None, help="latency of your instance in clocks (default: the library's value for the variant, given by --variant)")
    ap.add_argument("--variant", default=None, help="library variant id the latency is taken from")
    ap.add_argument("--vectors", type=int, default=None, help="random/edge vector count (default: exhaustive when the width is small)")
    ap.add_argument("--gap", type=int, default=25)
    a = ap.parse_args(argv)
    params = {k: int(v) for k, v in (p.split("=") for p in a.param)}
    vin, vexp, in_w, out_w, lat = plan(params, a.variant, a.vectors)
    if a.latency is not None:
        lat = a.latency
    wd = Path(tempfile.mkdtemp(prefix="arith_h_"))
    tb = wd / "tb_user.sv"
    tb.write_text(tb_text(a.dut, params))
    r = sim.run_stream("tb_user", [Path(x) for x in a.rtl], {}, vin, vexp, in_w, out_w, lat, gap_pct=a.gap, extra_tb=[tb])
    cov = coverage(fn_dir, vin, decode)
    ok = sim.ok(r) and all(v > 0 for v in cov.values())
    print(json.dumps({"result": {k: v for k, v in r.items() if k != "log"}, "latency_checked": lat, "coverage": cov, "pass": ok}, indent=1))
    if not sim.ok(r):
        print(r.get("log", ""))
    return 0 if ok else 1
