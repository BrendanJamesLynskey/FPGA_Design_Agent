"""Acceptance tests of p_ws2812_gen against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor
from model import COLOR, CTRL, DESIGN_ID, DIM, FRAMES, PIXELS, STATUS, Model, bits_for, waveform


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {})
        p = self.b.param
        self.t = (p("T0H"), p("T0L"), p("T1H"), p("T1L"))
        self.gap = p("RESET_CYCLES")
        self.m = Model()

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, line=lambda: int(self.dut.JC1.value), led=lambda: int(self.dut.LED.value))

    async def setup(self, color: int, pixels: int, dim: int) -> None:
        for off, v in ((COLOR, color), (PIXELS, pixels), (DIM, dim)):
            await self.b.write(off, v)
            self.m.write(off, v)

    async def go(self) -> None:
        mark = self.mon.mark()
        await self.b.write(CTRL, 1)
        self.m.write(CTRL, 1)
        color, pixels, dim = self.m.sent
        want = waveform(bits_for(color, pixels, dim), *self.t)
        await self.b.cycles(len(want) + self.gap + 400)
        self.m.finish()
        seq = self.mon.since("line", mark)
        start = next((i for i, v in enumerate(seq) if v), None)
        assert start is not None, "no data on JC1"
        got = seq[start: start + len(want)]
        assert got == want, f"frame differs at clock {next(i for i in range(len(want)) if got[i] != want[i])} of {len(want)}"
        assert not any(seq[start + len(want):]), "line high during or after the latch gap"
        assert not any(seq[:start])

    async def check(self) -> None:
        for off, name in ((COLOR, "COLOR"), (PIXELS, "PIXELS"), (DIM, "DIM"), (STATUS, "STATUS"), (FRAMES, "FRAMES")):
            await self.b.expect(off, self.m.read(off), name)


@cocotb.test()
async def test_identity_and_defaults(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check()
    await e.b.cycles(50)
    assert not any(e.mon.v["line"])


@cocotb.test()
async def test_one_pixel_exact_waveform(dut):
    e = Env(dut)
    await e.start()
    await e.setup(0x12A5C3, 1, 255)
    await e.go()
    await e.check()


@cocotb.test()
async def test_dimmer_and_pixel_count(dut):
    e = Env(dut)
    await e.start()
    await e.setup(0xFF8001, 3, 128)
    await e.go()
    await e.setup(0xFFFFFF, 2, 0)
    await e.go()
    await e.setup(0x0F0F0F, 0, 255)           # PIXELS clamps to 1
    assert e.m.pixels == 1
    await e.go()
    await e.check()


@cocotb.test()
async def test_go_while_busy_is_ignored(dut):
    e = Env(dut)
    await e.start()
    await e.setup(0xC0FFEE, 16, 200)           # 16 pixels: a long frame
    mark = e.mon.mark()
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    color, pixels, dim = e.m.sent
    want = waveform(bits_for(color, pixels, dim), *e.t)
    await e.b.write(CTRL, 1)                    # still sending
    e.m.write(CTRL, 1)
    await e.b.expect(STATUS, e.m.read(STATUS), "STATUS while busy")
    await e.b.cycles(len(want) + e.gap + 400)
    e.m.finish()
    seq = e.mon.since("line", mark)
    start = next(i for i, v in enumerate(seq) if v)
    assert seq[start: start + len(want)] == want and not any(seq[start + len(want):]), "the ignored go disturbed the line"
    await e.check()
    assert e.m.ignored == 1 and e.m.frames == 1


@cocotb.test()
async def test_random_frames(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(3):
        await e.setup(rng.randrange(1 << 24), rng.randrange(1, 5), rng.randrange(256))
        await e.go()
    await e.check()
