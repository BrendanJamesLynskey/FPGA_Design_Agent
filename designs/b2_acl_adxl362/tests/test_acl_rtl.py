"""pytest entry: acl_regs (SPI burst master) under cocotb + Icarus, against an ADXL362 model."""

from __future__ import annotations

from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent


def test_acl_regs_against_adxl362_model() -> None:
    sources = [s for s in sorted((DESIGN / "rtl").glob("*.sv")) if not s.name.endswith("_top.sv")]
    cocotb_run.run("b2_acl_adxl362", "tb_acl", sources + [HERE / "tb_acl.sv"], "acl_cocotb", HERE,
                   parameters={"HALF": 4})
