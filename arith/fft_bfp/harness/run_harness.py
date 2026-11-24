#!/usr/bin/env python3
"""Run the packaged verification harness of fft_bfp (arith brief 161, owner decision 24) against YOUR instance of the block. Standalone: needs this folder, Python 3 with cocotb 2.0.x, pyyaml,
and Icarus Verilog (iverilog); no other file of the repository.

    python3 run_harness.py --rtl my_fft_bfp.sv [more.sv ...] --top my_module --variant sdf --params '{"LOGN": 4, "W": 8, "TW": 10, "RND": 1, "ORDER": 0, "CMUL": 4, "TWSTAGES": 1, "MULSTAGES": 2}' --latency 41 [--mode all] [--checker] [--seed 1] [--n 3000]

--rtl      your source file(s) (the module and everything it instantiates)
--top      the module to test: it must have the ports of spec.md ("Ports") and the parameters you pass in --params, under the same names
--params   JSON object with a value for EVERY parameter of spec.md (the bench builds its model from them)
--latency  your instance's latency in clocks, as spec.md defines it for this block (a wrong value fails the run: that is deliberate)
--variant  which architecture's stall and gap rules your instance follows (the variants of this block: sdf, burst); the bench drives only what that variant permits
--mode     all (default) or one of: directed, levels, randomised, stalled, stalled_hard
--checker  also build chk_top.sv with the protocol / frame checkers of assertions.sv beside your instance; their error counters must stay 0
Exit status 0: every output matched the model bit for bit, the latency and the checkers were as specified, and (mode all) every coverage target of coverage.yaml was met."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FUNCTION = "fft_bfp"
MODES = ['directed', 'levels', 'randomised', 'stalled', 'stalled_hard']


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtl", nargs="+", required=True)
    ap.add_argument("--top", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--latency", type=int, required=True)
    ap.add_argument("--variant", default="sdf")
    ap.add_argument("--mode", default="all", choices=["all"] + MODES)
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
        sources += [str(HERE / "assertions.sv"), str(HERE / "chk_top.sv")]
        top = "chk_top"
        (build / "dut_defs.svh").write_text(f"`define DUT_MODULE {a.top}\n`define DUT_PARAMS #(" + ", ".join(f".{k}({k})" for k in params) + ")\n")
    modes = MODES if a.mode == "all" else [a.mode]
    sim = get_runner("icarus")
    sim.build(sources=sources, hdl_toplevel=top, parameters=hdl_params, build_dir=build / "sim_build", always=True, build_args=["-g2012", f"-I{build}"], timescale=("1ns", "1ps"))
    ok = True
    totals: dict[str, dict] = {}
    for t in modes:
        cov_out = build / f"coverage_{t}.json"
        env = {"PYTHONPATH": str(HERE), "ARITH_PARAMS": json.dumps(params), "ARITH_LAT": str(a.latency), "ARITH_SEED": str(a.seed), "ARITH_N": str(a.n), "ARITH_VARIANT": a.variant,
               "ARITH_COVER_FILE": str(HERE / "coverage.yaml"), "ARITH_COVER_OUT": str(cov_out)}
        try:
            res = sim.test(test_module=f"{FUNCTION}_cocotb", hdl_toplevel=top, testcase=t, build_dir=build / "sim_build", test_dir=HERE, parameters=hdl_params,
                           extra_env=env, results_xml=str(build / f"results_{t}.xml"), log_file=build / f"sim_{t}.log", timescale=("1ns", "1ps"))
            n, f = get_results(res)
            ok &= (n > 0 and f == 0)
            print(f"{t}: {n} test(s), {f} failed")
        except SystemExit:
            print(f"{t}: FAILED (see {build / f'sim_{t}.log'})")
            ok = False
        if cov_out.exists():
            for b in json.loads(cov_out.read_text())["bins"]:
                tot = totals.setdefault(b["name"], {"min": b["min"], "min_if": b.get("min_if"), "hits": 0})
                tot["hits"] += b["hits"]
    if a.mode == "all" and not a.no_coverage_check:
        import yaml
        wanted = {b["name"]: b for b in yaml.safe_load((HERE / "coverage.yaml").read_text())["bins"]}
        miss = []
        for name, b in wanted.items():
            if b.get("min_if") and not eval(b["min_if"], {}, {"p": params}):
                continue
            hits = totals.get(name, {"hits": 0})["hits"]
            if hits < b["min"]:
                miss.append(f"{name} {hits}/{b['min']}")
        print(f"coverage: {len(wanted) - len(miss)} of {len(wanted)} bins met" + (f"; NOT met: {', '.join(miss)}" if miss else ""))
        ok &= not miss
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
