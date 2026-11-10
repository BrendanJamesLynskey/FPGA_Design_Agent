"""pytest entry: the rig's checkers and saturating record under cocotb + Icarus (sim/chk_cocotb.py)."""

from __future__ import annotations

from pathlib import Path

RIG = Path(__file__).resolve().parents[1]
ROOT = RIG.parents[1]


def test_checkers() -> None:
    from cocotb_tools.runner import get_runner

    srcs = [RIG / "rtl" / f for f in ("rig_pkg.sv", "cdc_lib.sv", "rig_check.sv")] + [RIG / "sim" / "tb_chk.sv"]
    build = ROOT / "build" / "sim" / "cdc_checkers"
    r = get_runner("icarus")
    r.build(sources=[str(s) for s in srcs], hdl_toplevel="tb_chk", defines={"CDC_SIM": 1}, build_dir=build,
            timescale=("1ns", "1ps"), always=True, build_args=["-g2012"])
    r.test(test_module="chk_cocotb", hdl_toplevel="tb_chk", build_dir=build, test_dir=RIG / "sim",
           results_xml=str(build / "results.xml"), log_file=build / "sim.log", timescale=("1ns", "1ps"))
