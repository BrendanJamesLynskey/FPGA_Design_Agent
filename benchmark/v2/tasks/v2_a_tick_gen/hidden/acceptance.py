"""Acceptance tests of v2_a_tick_gen against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from cocotb.triggers import ReadOnly, RisingEdge
from model import DESIGN_ID, DIV, RESET_DIV, TICKS, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut, self.b, self.m = dut, Board(dut, {}), Model()
        self.log: list[tuple[int, int]] = []       # (LED[0], LED[1]) per rising edge
        self.mon = None

    async def start(self) -> None:
        await self.b.start()
        self.mon = cocotb.start_soon(self.watch())

    async def watch(self) -> None:
        while True:
            await RisingEdge(self.b.clk)
            await ReadOnly()
            v = int(self.dut.LED.value)
            self.log.append((v & 1, v >> 1 & 1))

    def take(self) -> list[tuple[int, int]]:
        out, self.log = self.log, []
        return out

    async def set_div(self, v: int) -> None:
        await self.b.write(DIV, v)
        self.m.write_div(v)

    async def check_run(self, periods: float = 4.0) -> int:
        """Wait for the first tick after a DIV write, align the model there, and compare 4 periods clock by clock.
        Returns the number of ticks compared."""
        n = self.m.div
        self.take()
        for _ in range(3 * n + 40):
            await self.b.cycles(1)
            if self.log and self.log[-1][0]:
                break
        assert self.log and self.log[-1][0], f"no tick within {3 * n + 40} clocks of a DIV = {n} write"
        self.m.led1 = self.log[-1][1]
        self.m.align()
        self.take()
        want = []
        for _ in range(int(periods * max(n, 3))):
            want.append(self.m.clock())
        await self.b.cycles(len(want))
        got = self.take()[:len(want)]
        assert len(got) == len(want)
        for i, (g, w) in enumerate(zip(got, want)):
            assert g == w, f"DIV = {n}, clock {i} after a tick: LED[1:0] (led1, tick) RTL {g[::-1]}, model {w[::-1]}"
        return sum(t for t, _ in want)


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.b.expect(DIV, RESET_DIV, "DIV at reset")
    await e.b.write(DIV, 0)
    await e.b.write(TICKS, 0)
    await e.b.reset()
    e.m = Model()
    e.take()
    await e.b.expect(DIV, RESET_DIV, "DIV after a second reset")
    assert await e.check_run() >= 4                 # the generator runs from reset with DIV = 8


@cocotb.test()
async def test_pulse_one_clock_wide(dut):
    """A tick is one clock wide (an enable), not a divided clock: no two ticks on consecutive clocks for DIV >= 2."""
    e = Env(dut)
    await e.start()
    for n in (2, 3, 4, 10, 33):
        await e.set_div(n)
        await e.check_run()
        e.take()
    await e.set_div(7)
    e.take()
    await e.b.cycles(60)
    log = e.take()
    t = [x[0] for x in log]
    assert 8 <= sum(t) <= 10 and all(not (a and b) for a, b in zip(t, t[1:])), "ticks must be one clock wide"


@cocotb.test()
async def test_exact_spacing_many_values(dut):
    e = Env(dut)
    await e.start()
    for n in (1, 2, 3, 5, 8, 17, 100, 255, 256, 257, 300, 1000):
        await e.set_div(n)
        await e.check_run(periods=3.0)


@cocotb.test()
async def test_zero_stops_and_restarts(dut):
    e = Env(dut)
    await e.start()
    await e.set_div(5)
    await e.check_run()
    await e.set_div(0)
    await e.b.cycles(6)
    e.take()
    await e.b.cycles(80)
    got = e.take()
    assert not any(t for t, _ in got), "DIV = 0 must give no ticks"
    led1 = got[-1][1]
    await e.b.expect(DIV, 0, "DIV")
    await e.set_div(6)
    await e.check_run()
    assert led1 in (0, 1)


@cocotb.test()
async def test_div_is_16_bits(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(DIV, 0x1_0000 | 12)             # only [15:0]: 12
    e.m.write_div(12)
    await e.b.expect(DIV, 12, "DIV")
    await e.check_run()
    await e.b.write(DIV, 0xFFFF_0000)               # 0 in [15:0]: stopped
    e.m.write_div(0)
    await e.b.expect(DIV, 0, "DIV")
    await e.b.cycles(40)


@cocotb.test()
async def test_tick_count_and_clear(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(DIV, 0)
    await e.b.cycles(20)
    await e.b.write(TICKS, 0xFFFF_FFFF)
    await e.b.expect(TICKS, 0, "TICKS after a clear")
    for n, span in ((3, 700), (1, 400), (50, 4000)):
        e.take()
        await e.b.write(DIV, n)
        await e.b.cycles(span)
        await e.b.write(DIV, 0)
        await e.b.cycles(4 * n if n > 1 else 8)
        seen = sum(t for t, _ in e.take())
        e.m.add_ticks(seen)
        await e.b.expect(TICKS, e.m.read(TICKS), f"TICKS after {seen} ticks at DIV = {n}")
    assert e.m.ticks > 255
    await e.b.write(TICKS, 5)
    e.m.clear_ticks()
    await e.b.expect(TICKS, 0, "TICKS after a clear")


@cocotb.test()
async def test_count_is_32_bits(dut):
    """More than 65535 ticks: DIV = 1 for 66000 clocks."""
    e = Env(dut)
    await e.start()
    await e.b.write(DIV, 0)
    await e.b.write(TICKS, 0)
    e.take()
    await e.b.write(DIV, 1)
    await e.b.cycles(66_000)
    await e.b.write(DIV, 0)
    await e.b.cycles(8)
    seen = sum(t for t, _ in e.take())
    assert seen > 65_536, f"only {seen} ticks seen"
    await e.b.expect(TICKS, seen, "TICKS after more than 65535 ticks")
    await e.b.write(TICKS, 0)


@cocotb.test()
async def test_random_div_sequence(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(8):
        await e.set_div(rng.choice([rng.randrange(1, 12), rng.randrange(12, 400), 0, 1]))
        if e.m.div:
            await e.check_run(periods=3.0)
        else:
            await e.b.cycles(30)
    for off in (0x02, 0x40, 0x7F):
        await e.b.expect(off, 0, "unmapped")
