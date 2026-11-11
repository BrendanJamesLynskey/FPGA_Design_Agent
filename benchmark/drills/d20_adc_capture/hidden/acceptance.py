"""Acceptance tests of d20_adc_capture against model.py (hidden from the agent). The I/O timing constraints are graded
separately (../lib/grade_io.py, on the agent's routed build)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from cocotb.triggers import FallingEdge, RisingEdge
from model import CLEAR, DESIGN_ID, IDLE, LAST, MAX, MIN, bits, min_max


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, bits(IDLE))

    async def drive(self, sample: int, hold: int = 40) -> None:
        """Put a sample on the pins just after a rising edge (as the ADC does) and hold it."""
        await RisingEdge(self.b.clk)
        for p, v in bits(sample).items():
            getattr(self.dut, p).value = v
        await self.b.cycles(hold)

    async def leds(self) -> int:
        await FallingEdge(self.b.clk)
        return int(self.dut.LED.value)


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.b.start()
    assert await e.b.shell_id() == DESIGN_ID
    # the pins hold IDLE through and after reset, so MIN and MAX have seen only IDLE
    for off, want, what in ((LAST, IDLE, "LAST"), (MIN, IDLE, "MIN"), (MAX, IDLE, "MAX"), (CLEAR, 0, "CLEAR"),
                            (0x04, 0, "unmapped 0x04"), (0x7F, 0, "unmapped 0x7F")):
        await e.b.expect(off, want, f"{what} at reset")


@cocotb.test()
async def test_last_and_leds_follow_the_pins(dut):
    e = Env(dut)
    await e.b.start()
    for s in (0x5A, 0xA5, 0x01, 0x80, 0xFF, 0x00, 0x3C):
        await e.drive(s)
        led = await e.leds()
        assert led == s, f"LED = {led:#06x} with sample {s:#04x} on the pins, want LED[7:0] = sample and LED[15:8] = 0"
        await e.b.expect(LAST, s, f"LAST with sample {s:#04x} on the pins")


@cocotb.test()
async def test_min_max_and_clear(dut):
    e = Env(dut)
    await e.b.start()
    seq = [0x40, 0x10, 0x90, 0x22]
    for s in seq:
        await e.drive(s)
    lo, hi = min_max(seq)
    await e.b.expect(MIN, lo, f"MIN after {[hex(x) for x in seq]}")
    await e.b.expect(MAX, hi, f"MAX after {[hex(x) for x in seq]}")
    await e.b.write(CLEAR, 1)
    await e.drive(0x22, hold=4)
    seq2 = [0x22, 0x33, 0x2A]
    for s in seq2[1:]:
        await e.drive(s)
    lo, hi = min_max(seq2)
    await e.b.expect(MIN, lo, f"MIN after a CLEAR and {[hex(x) for x in seq2]}")
    await e.b.expect(MAX, hi, f"MAX after a CLEAR and {[hex(x) for x in seq2]}")


@cocotb.test()
async def test_short_pulses_reach_min_max(dut):
    """A sample held for only a few clocks still updates MIN and MAX (they update on every clock)."""
    e = Env(dut)
    await e.b.start()
    await e.drive(0x50, hold=30)
    await e.b.write(CLEAR, 1)
    await e.drive(0x50, hold=30)
    await e.drive(0xF0, hold=3)
    await e.drive(0x50, hold=3)
    await e.drive(0x05, hold=3)
    await e.drive(0x50, hold=30)
    await e.b.expect(MAX, 0xF0, "MAX after a 3-clock sample of 0xF0")
    await e.b.expect(MIN, 0x05, "MIN after a 3-clock sample of 0x05")


@cocotb.test()
async def test_random_samples(dut):
    e = Env(dut)
    await e.b.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    await e.b.write(CLEAR, 1)
    seq = [rng.randrange(256) for _ in range(12)]
    for s in seq:
        await e.drive(s, hold=6)
    await e.drive(seq[-1], hold=30)
    lo, hi = min_max(seq)
    await e.b.expect(MIN, lo, "MIN after random samples")
    await e.b.expect(MAX, hi, "MAX after random samples")
    await e.b.expect(LAST, seq[-1], "LAST after random samples")
