"""pytest entry: b30_hil_audio_top under cocotb + Icarus (shell at 8 clocks a bit, a 40 000-clock frequency gate)."""
from __future__ import annotations

from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]
IP = ROOT / "ip_lib"


def test_hil_audio_instruments_against_models() -> None:
    sources = (cocotb_run.SHELL_RTL + [HERE / "xadc_sim.sv"] +
               [f for b in ("dds_awg", "freq_duty_counter", "logic_analyser", "frame_crc") for f in sorted((IP / b / "rtl").glob("*.sv"))] +
               sorted((DESIGN / "rtl").glob("*.sv")))
    cocotb_run.run("b30_hil_audio", "b30_hil_audio_top", sources, "hil_audio_cocotb", HERE,
                   parameters={"CLKS_PER_BIT": 8, "TIMEOUT_CYCLES": 400, "FD_GATE_CLKS": 40000}, seed=1)
