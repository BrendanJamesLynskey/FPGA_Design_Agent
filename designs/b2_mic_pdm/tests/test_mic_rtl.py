"""pytest entry: mic_regs (PDM clock and bit statistics) under cocotb + Icarus, against a microphone model."""

from __future__ import annotations

from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent


def test_mic_regs_against_microphone_model() -> None:
    sources = [s for s in sorted((DESIGN / "rtl").glob("*.sv")) if not s.name.endswith("_top.sv")]
    cocotb_run.run("b2_mic_pdm", "tb_mic", sources + [HERE / "tb_mic.sv"], "mic_cocotb", HERE,
                   parameters={"HALF": 4})
