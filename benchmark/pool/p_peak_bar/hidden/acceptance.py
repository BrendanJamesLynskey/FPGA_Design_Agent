"""Acceptance tests of p_peak_bar against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from benchmark.pool.poollib import Monitor, runs
from model import DESIGN_ID, LEVEL, MAXRAW, PEAK, Model

CLR = 0x8000


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        self.m = Model()
        self.decay = self.b.param("DECAY_CYCLES")

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, led=lambda: int(self.dut.LED.value))

    async def level(self, raw: int, clr: bool = False) -> None:
        self.dut.SW.value = raw | (CLR if clr else 0)
        self.m.level(raw)
        if clr:
            self.m.clear_peak()
        await self.b.cycles(8)

    async def check_led(self) -> None:
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:016b} != model {self.m.leds():016b}"

    async def check_regs(self) -> None:
        for off, name in ((LEVEL, "LEVEL"), (PEAK, "PEAK"), (MAXRAW, "MAXRAW")):
            await self.b.expect(off, self.m.read(off), name)


@cocotb.test()
async def test_identity_and_dark(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_led()
    await e.check_regs()


@cocotb.test()
async def test_bar_lengths(dut):
    e = Env(dut)
    await e.start()
    for raw in (1, 16, 17, 100, 240, 241, 255):
        await e.level(raw)
        await e.check_led()
    await e.b.expect(LEVEL, 16, "LEVEL")
    await e.b.expect(PEAK, 16, "PEAK")


@cocotb.test()
async def test_marker_creeps_down_at_the_set_rate(dut):
    e = Env(dut)
    await e.start()
    await e.level(0xA0)                       # N = 10, marker 10
    await e.check_led()
    await e.level(0x30)                       # N = 3, marker held at 10
    await e.check_led()
    mark = e.mon.mark()
    want = e.m.decay_leds()
    await e.b.cycles(e.decay * (len(want) + 2))
    seq = runs(e.mon.since("led", mark))
    vals = [v for v, _, _ in seq]
    assert vals == [e.m.leds()] + want, f"LED words {vals}, want {[e.m.leds()] + want}"
    inner = [n for _, _, n in seq[1:-1]]
    assert all(n == e.decay for n in inner), f"steps {inner} clocks apart, want {e.decay}"
    assert e.decay - 40 <= seq[0][2] <= e.decay + 8, f"first step after {seq[0][2]} clocks"


@cocotb.test()
async def test_clear_pulls_marker_down(dut):
    e = Env(dut)
    await e.start()
    await e.level(0xF0)
    await e.level(0x20)
    await e.check_led()
    await e.level(0x20, clr=True)
    await e.check_led()
    await e.b.expect(PEAK, e.m.read(PEAK), "PEAK after clear")
    await e.level(0x20)
    await e.check_led()


@cocotb.test()
async def test_maxraw_register(dut):
    e = Env(dut)
    await e.start()
    for raw in (30, 200, 90):
        await e.level(raw)
    await e.b.expect(MAXRAW, 200, "MAXRAW")
    await e.b.write(MAXRAW, 0)
    e.m.write(MAXRAW, 0)
    await e.b.expect(MAXRAW, 90, "MAXRAW after clear")


@cocotb.test()
async def test_random_levels(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(5):
        hi, lo = rng.randrange(1, 256), rng.randrange(0, 256)
        await e.level(hi)
        await e.level(lo)
        await e.check_led()
        await e.b.expect(PEAK, e.m.read(PEAK), "PEAK")
        await e.b.expect(LEVEL, e.m.read(LEVEL), "LEVEL")
        await e.level(lo, clr=True)
        await e.check_led()
        await e.level(lo)
