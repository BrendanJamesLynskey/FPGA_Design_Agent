"""pytest entry: the fabric PRBS generator/checker under cocotb + Icarus, against the reference model."""

from __future__ import annotations

from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]


def test_prbs_cocotb() -> None:
    srcs = [DESIGN / "rtl" / "prbs64.sv", DESIGN / "sim" / "prbs_link.sv"]
    cocotb_run.run("b56a_prbs", "prbs_link", srcs, "prbs_cocotb", HERE, extra_env={"PYTHONPATH": str(ROOT)})
