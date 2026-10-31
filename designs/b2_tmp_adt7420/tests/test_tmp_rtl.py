"""pytest entry: tmp_regs (I2C pointer-read engine) under cocotb + Icarus, against an ADT7420 model."""

from __future__ import annotations

from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent


def test_tmp_regs_against_adt7420_model() -> None:
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    sources = [s for s in sources if not s.name.endswith("_top.sv")] + [HERE / "tb_tmp.sv"]
    cocotb_run.run("b2_tmp_adt7420", "tb_tmp", sources, "tmp_cocotb", HERE, parameters={"QUARTER": 5})
