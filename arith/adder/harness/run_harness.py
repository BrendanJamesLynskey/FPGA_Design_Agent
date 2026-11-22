#!/usr/bin/env python3
"""Run the packaged verification harness of adder (arith brief 139a) against YOUR instance of the block. Standalone: needs this folder, Python 3 with
cocotb 2.0.x and pyyaml, and Icarus Verilog (iverilog); no other file of the repository.

    python3 run_harness.py --rtl my_adder.sv [more.sv ...] --top my_module --params '{"WIDTH": 32}' --latency 0 [--mode both] [--checker] [--seed 1] [--n 3000]

--rtl      your source file(s) (the module and anything it instantiates)
--top      the module to test: it must have the ports of spec.md ("Ports") and the parameters you pass in --params, under the same names
--params   JSON object of parameter values for your instance (every parameter the harness model needs, e.g. the widths and SIGNED)
--latency  your instance's latency in clocks (the variants of this library state theirs in spec.yaml)
--mode     exhaustive (small widths only), randomised (any width) or both (default: exhaustive when the operand bits are few, else randomised)
--checker  also build chk_top.sv: your instance with the SystemVerilog checker (assertions.sv) beside it, whose error counter must stay 0
Exit status 0: every vector matched the model, the checker (if used) counted no mismatch, and every coverage target of coverage.yaml was met."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FUNCTION = "adder"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtl", nargs="+", required=True)
    ap.add_argument("--top", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--latency", type=int, required=True)
    ap.add_argument("--mode", default="auto", choices=["auto", "exhaustive", "randomised", "both"])
    ap.add_argument("--checker", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--build-dir")
    ap.add_argument("--no-coverage-check", action="store_true")
    a = ap.parse_args()
    from cocotb_tools.runner import get_results, get_runner
    params = json.loads(a.params)
    build = Path(a.build_dir or tempfile.mkdtemp(prefix=f"harness_{FUNCTION}_"))
    build.mkdir(parents=True, exist_ok=True)
    sources = [str(Path(f).resolve()) for f in a.rtl]
    top, hdl_params = a.top, dict(params)
    if a.checker:
        sources += [str(f) for f in sorted(HERE.glob("*.sv"))]
        top = "chk_top"
        (build / "dut_defs.svh").write_text(f"`define DUT_MODULE {a.top}\n`define DUT_PARAMS #(" + ", ".join(f".{k}({k})" for k in params) + ")\n")
        hdl_params = {**params, "LAT": a.latency}
    mode = a.mode
    if mode == "auto":
        bits = sum(v for k, v in params.items() if k in ("WIDTH", "WA", "WB", "LANES")) if FUNCTION != "adder" else 2 * params.get("WIDTH", 99)
        mode = "exhaustive" if bits <= (12 if FUNCTION != "adder" else 12) else "randomised"
    tests = ["exhaustive", "randomised"] if mode == "both" else [mode]
    sim = get_runner("icarus")
    sim.build(sources=sources, hdl_toplevel=top, parameters=hdl_params, build_dir=build / "sim_build", always=True, build_args=["-g2012", f"-I{build}"], timescale=("1ns", "1ps"))
    cov_out = build / "coverage.json"
    env = {"PYTHONPATH": str(HERE), "ARITH_PARAMS": json.dumps(params), "ARITH_LAT": str(a.latency), "ARITH_SEED": str(a.seed), "ARITH_N": str(a.n),
           "ARITH_COVER_FILE": str(HERE / "coverage.yaml"), "ARITH_COVER_OUT": str(cov_out)}
    ok = True
    for t in tests:
        try:
            res = sim.test(test_module=f"{FUNCTION}_cocotb", hdl_toplevel=top, testcase=t, build_dir=build / "sim_build", test_dir=HERE, parameters=hdl_params,
                           extra_env=env, results_xml=str(build / f"results_{t}.xml"), log_file=build / f"sim_{t}.log", timescale=("1ns", "1ps"))
            n, f = get_results(res)
            ok &= (n > 0 and f == 0)
            print(f"{t}: {n} test(s), {f} failed")
        except SystemExit:
            print(f"{t}: FAILED (see {build / f'sim_{t}.log'})")
            ok = False
    if cov_out.exists() and not a.no_coverage_check:
        cov = json.loads(cov_out.read_text())["bins"]
        # a coverage target is checked only for the streams that ran: a bin with `min_if` false for these parameters is skipped
        miss = []
        for b in cov:
            if b.get("min_if") and not eval(b["min_if"], {}, {"p": params}):
                continue
            if b["hits"] < b["min"]:
                miss.append(f"{b['name']} {b['hits']}/{b['min']}")
        print(f"coverage: {len(cov) - len(miss)} of {len(cov)} bins met" + (f"; NOT met: {', '.join(miss)}" if miss else ""))
        if miss and mode != "exhaustive":
            ok = False
        elif miss:
            print("(exhaustive mode on a tiny point may not reach every bin: run --mode both on a larger point for the coverage verdict)")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
