"""Acceptance tests of p_moving_avg against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import AVG, CLIP, COUNT, CTRL, DESIGN_ID, SAMPLE, SUM, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {})
        self.m = Model()

    async def start(self) -> None:
        await self.b.start()

    async def feed(self, *xs: int, check: bool = True) -> None:
        for x in xs:
            await self.b.write(SAMPLE, x)
            self.m.write(SAMPLE, x)
        if check:
            await self.check()

    async def check(self) -> None:
        await self.b.cycles(30)
        for off, name in ((SAMPLE, "SAMPLE"), (AVG, "AVG"), (SUM, "SUM"), (COUNT, "COUNT"), (CLIP, "CLIP")):
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check()


@cocotb.test()
async def test_filling_the_window(dut):
    e = Env(dut)
    await e.start()
    for x in (10, 21, 33, 40, 51, 62):
        await e.feed(x)
    assert e.m.read(COUNT) == 6
    await e.feed(70, 80)
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.check()
    await e.feed(7)


@cocotb.test()
async def test_clipping(dut):
    e = Env(dut)
    await e.start()
    await e.feed(1000, 1000, 1000, 1000, 1000, 1000)
    await e.feed(4000)                         # pulled in to 1500
    await e.feed(0)
    await e.b.write(CLIP, 100)
    e.m.write(CLIP, 100)
    await e.feed(0, 4095, 2000)
    await e.b.write(CLIP, 0)
    e.m.write(CLIP, 0)
    await e.feed(5, 6, 7)                      # CLIP 0: every sample becomes the current average
    await e.b.write(CLIP, 0x1FFF)
    e.m.write(CLIP, 0x1FFF)
    await e.feed(1, 4095)


@cocotb.test()
async def test_not_clipped_while_filling(dut):
    """A textbook filter clips from the first sample; this one lets the first six in unchanged."""
    e = Env(dut)
    await e.start()
    await e.feed(4000, 0, 4000, 0, 4000, 0)
    assert e.m.read(SUM) == 12000
    await e.feed(4000)


@cocotb.test()
async def test_random_samples(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for i in range(10):
        if i == 5:
            c = rng.randrange(1, 400)
            await e.b.write(CLIP, c)
            e.m.write(CLIP, c)
        await e.feed(rng.choice([rng.randrange(4096), rng.randrange(900, 1100)]), check=False)
    await e.check()
