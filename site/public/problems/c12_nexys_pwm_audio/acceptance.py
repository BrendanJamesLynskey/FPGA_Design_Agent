"""Acceptance tests of c12_nexys_pwm_audio against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board
from cocotb.triggers import ReadOnly, RisingEdge
from model import DESIGN_ID, GAIN, SAMPLE, SOUT, expected, steps


def s16(v: int) -> int:
    return v - 65536 if v & 0x8000 else v


async def measure(b: Board, dut, clocks: int = 4096) -> tuple[int, bool]:
    """Clocks with the (resolved) pin low over `clocks` consecutive clocks, and whether AUD_SD stayed 1."""
    low, sd = 0, True
    for _ in range(clocks):
        await RisingEdge(b.clk)
        await ReadOnly()
        low += int(dut.pwm.value) == 0
        sd &= int(dut.AUD_SD.value) == 1
        assert int(dut.pwm_pd.value) == 0, "AUD_PWM was driven high (with a pull-down on the pin it read 1)"
    await RisingEdge(b.clk)
    return low, sd


@cocotb.test(timeout_time=400_000_000, timeout_unit="ns")
async def test_identity_and_reset(dut):
    b = Board(dut, {})
    await b.start()
    assert await b.shell_id() == DESIGN_ID
    await b.expect(SAMPLE, 0, "SAMPLE after reset")
    await b.expect(SOUT, 0, "SOUT after reset")


@cocotb.test(timeout_time=2_000_000_000, timeout_unit="ns")
async def test_gain_clamp_and_pwm_duty(dut):
    b = Board(dut, {})
    await b.start()
    st = steps()
    for k, (s, e) in enumerate(zip(st, expected(st))):
        what = f"step {k} (reset {s['reset']}, write {s['write']}, sample {s['sample']})"
        if s["reset"]:
            await b.reset()
        if s["write"] is not None:
            await b.write(GAIN, s["write"])
        await b.write(SAMPLE, s["sample"] & 0xFFFF)
        assert s16(await b.read(SOUT)) == e["sample_out"], f"{what}: sample_out {s16(await b.read(SOUT))}, expected {e['sample_out']}"
        await b.cycles(2048)
        low, sd = await measure(b, dut)
        assert sd, f"{what}: AUD_SD was not always high"
        assert low == 4 * e["low_per_period"], f"{what}: {low / 4} clocks pulled low per period, expected {e['low_per_period']}"
