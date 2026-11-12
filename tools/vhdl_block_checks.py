#!/usr/bin/env python3
"""Run the block-level drills of brief 55 on VHDL translations, natively under GHDL (no test shell, no netlist).

    python3 tools/vhdl_block_checks.py --cdc <dir with cdcfx_c*.vhd> [--axi <dir with axil_regs.vhd> --axi-tests <dir>]
                                       [--json OUT]

- CDC: each ``cdcfx_<name>.vhd`` runs the brief 16 fixture's own cocotb test (flow/tests/fixtures/cdc_mutants/tb,
  clk_a 10 ns, clk_b 7 ns, random traffic, checked against the sent data), the same test the SystemVerilog fixture
  passes under Icarus. Synchroniser-delay injection (flow/cdc_inject.py) reads SystemVerilog and is not applied.
- AXI4-Lite: ``axil_regs.vhd`` runs the knowledge bank's AXI4-Lite cocotb test (``axil_random``, in the private bank's
  tools/axi_examples; pass its directory as --axi-tests), the test its Verilog original passes under Icarus.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FX = ROOT / "flow" / "tests" / "fixtures" / "cdc_mutants"


def run_cdc(vh: Path, build: Path) -> dict:
    from flow import cocotb_run
    name = vh.stem
    os.environ["CDCFX_NAME"] = name
    os.environ.pop("FDA_CDC_INJECT_SEED", None)
    os.environ["SIM"] = "ghdl"
    try:
        cocotb_run.run(f"vhdl_{name}", name, [vh], "cdcfx_tb", FX / "tb", seed=1, build_root=build)
        return {"drill": name, "sim": "ghdl", "pass": True}
    except AssertionError as e:
        return {"drill": name, "sim": "ghdl", "pass": False, "error": str(e)[-1500:]}


def run_axi(vh: Path, tests: Path, build: Path) -> dict:
    from cocotb_tools.runner import get_results, get_runner

    from flow import vhdl
    os.environ["TOP"] = "axil_regs"
    r = get_runner("ghdl")
    bd = build / "vhdl_axil_regs"
    r.build(sources=[str(vh)], hdl_toplevel="axil_regs", build_dir=bd, always=True,
            build_args=[f"--std={vhdl.STD}"])
    try:
        xml = r.test(hdl_toplevel="axil_regs", test_module="axi_cocotb_tests", testcase=["axil_random"], build_dir=bd,
                     test_dir=tests, results_xml=str(bd / "results.xml"), test_args=[f"--std={vhdl.STD}", f"--workdir={bd}"])
        n, f = get_results(xml)
        return {"drill": "axil_regs", "sim": "ghdl", "pass": n > 0 and f == 0, "tests": n, "failed": f}
    except (SystemExit, Exception) as e:  # noqa: BLE001 - the runner raises when a test fails
        return {"drill": "axil_regs", "sim": "ghdl", "pass": False, "error": f"{type(e).__name__}: {str(e)[-800:]}"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cdc", type=Path)
    ap.add_argument("--axi", type=Path)
    ap.add_argument("--axi-tests", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    build = Path(tempfile.mkdtemp(prefix="vhdl_blocks_"))
    out = []
    if a.cdc:
        for vh in sorted(a.cdc.glob("cdcfx_*.vhd")):
            out.append(run_cdc(vh, build))
    if a.axi:
        if not a.axi_tests:
            ap.error("--axi needs --axi-tests (the bank's tools/axi_examples directory)")
        out.append(run_axi(a.axi / "axil_regs.vhd", a.axi_tests, build))
    for r in out:
        print(f"{r['drill']:12s} {'PASS' if r['pass'] else 'FAIL'}  {r.get('error', '')[:300]}")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(out, indent=1) + "\n")
    return 0 if out and all(r["pass"] for r in out) else 1


if __name__ == "__main__":
    raise SystemExit(main())
