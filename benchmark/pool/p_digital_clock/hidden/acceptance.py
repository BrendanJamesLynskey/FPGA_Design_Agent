"""Acceptance tests of p_digital_clock against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek, scan_display
from model import DAYS, DESIGN_ID, TIME, UPTIME, Model

PAUSE, TWELVE = 2, 1


def pack(h: int, m: int, s: int) -> int:
    return s | m << 6 | h << 12


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": PAUSE})            # paused from reset: nothing moves until released
        self.m = Model()
        self.tick = self.b.param("TICK_CYCLES")
        self.slot = 1 << self.b.param("REFRESH_BITS")
        self.sw = PAUSE

    async def start(self) -> None:
        await self.b.start()

    async def setsw(self, v: int) -> None:
        self.sw = v
        self.dut.SW.value = v
        self.m.twelve = bool(v & TWELVE)
        await self.b.cycles(5)

    async def set_time(self, h: int, m: int, s: int) -> None:
        await self.b.write(TIME, pack(h, m, s))
        self.m.write(TIME, pack(h, m, s))

    async def run_seconds(self, n: int) -> None:
        """Run the clock for about n seconds, pause, and bring the model to the seconds the RTL counted."""
        before = await self.b.read(UPTIME)
        self.m.uptime = before
        await self.setsw(self.sw & ~PAUSE)
        await self.b.cycles(n * self.tick + self.tick // 2)
        await self.setsw(self.sw | PAUSE)
        k = await self.b.read(UPTIME) - before
        assert abs(k - n) <= 1, f"{k} seconds counted in about {n}"
        self.m.seconds(k)

    async def check(self) -> None:
        for off, name in ((TIME, "TIME"), (DAYS, "DAYS"), (UPTIME, "UPTIME")):
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(bool(self.sw & PAUSE)), f"LED {led:04X} != {self.m.leds(bool(self.sw & PAUSE)):04X}"
        seen = await scan_display(self.dut, self.b.clk, self.slot)
        want = self.m.display()
        assert seen == want, f"display {seen} != model {want}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check()


@cocotb.test()
async def test_counts_and_rolls_over_midnight(dut):
    e = Env(dut)
    await e.start()
    await e.set_time(23, 59, 57)
    await e.run_seconds(5)
    await e.check()
    assert e.m.days == 1 and e.m.h == 0
    await e.b.write(DAYS, 4)
    e.m.write(DAYS, 4)
    await e.check()


@cocotb.test()
async def test_pause_holds_the_partial_second(dut):
    e = Env(dut)
    await e.start()
    await e.set_time(1, 2, 3)
    await e.setsw(0)
    await e.b.cycles(e.tick // 2 + 200)         # half a second in
    await e.setsw(PAUSE)
    await e.b.cycles(3 * e.tick)                # held for several seconds
    await e.check()
    assert e.m.read(UPTIME) == 0 and e.m.s == 3
    await e.setsw(0)
    await e.b.cycles(e.tick // 2 + 20 + e.tick // 4)
    await e.setsw(PAUSE)
    await e.b.cycles(10)
    u = await e.b.read(UPTIME)
    assert u == 1, f"the held half second plus half a second should make one second; UPTIME = {u}"
    e.m.seconds(1)
    await e.check()


@cocotb.test()
async def test_12_hour_display(dut):
    e = Env(dut)
    await e.start()
    for hms in ((0, 0, 0), (0, 59, 59), (9, 8, 7), (12, 0, 0), (13, 5, 6), (23, 59, 59)):
        await e.setsw(PAUSE | TWELVE)
        await e.set_time(*hms)
        await e.check()
        await e.setsw(PAUSE)
        await e.check()


@cocotb.test()
async def test_invalid_time_writes(dut):
    e = Env(dut)
    await e.start()
    await e.set_time(10, 20, 30)
    for bad in (pack(24, 0, 0), pack(0, 60, 0), pack(0, 0, 60), pack(31, 63, 63)):
        await e.b.write(TIME, bad)
        e.m.write(TIME, bad)
        await e.b.expect(TIME, pack(10, 20, 30), "TIME after a bad write")
    await e.check()


@cocotb.test()
async def test_random_times(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(4):
        await e.setsw(PAUSE | (TWELVE if rng.random() < 0.5 else 0))
        await e.set_time(rng.randrange(24), rng.choice([0, 59, rng.randrange(60)]), rng.choice([55, 56, 57, rng.randrange(60)]))
        await e.run_seconds(rng.randrange(1, 6))
        await e.check()
