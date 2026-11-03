"""Acceptance tests of p_rate_mult against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor
from model import CTRL, DESIGN_ID, M, N, TICKS, Model


def rotation_match(obs: list[int], pat: list[int]) -> bool:
    """obs repeats pat, starting at some phase."""
    k = len(pat)
    return any(all(obs[i] == pat[(i + r) % k] for i in range(len(obs))) for r in range(k))


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        self.m = Model()

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, tick=lambda: int(self.dut.LED.value) & 1, flip=lambda: (int(self.dut.LED.value) >> 1) & 1)

    async def setup(self, n: int, m: int) -> None:
        await self.b.write(N, n)
        self.m.write(N, n)
        await self.b.write(M, m)
        self.m.write(M, m)

    async def burst(self, periods: int = 4) -> list[int]:
        """Enable for periods x M_E clocks (plus slack), return the ticks seen strictly inside the run."""
        self.dut.SW.value = 1
        await self.b.cycles(12)
        mark = self.mon.mark()
        await self.b.cycles(periods * self.m.m_e)
        seq = self.mon.since("tick", mark)
        self.dut.SW.value = 0
        await self.b.cycles(10)
        return seq

    async def check_pattern(self, n: int, m: int) -> None:
        await self.setup(n, m)
        seq = await self.burst()
        pat = self.m.pattern()
        assert rotation_match(seq, pat), f"N={n} M={m}: ticks {seq[:3 * len(pat)]} are not the pattern {pat} at any phase"
        assert sum(seq[:len(pat)]) == self.m.n_e


@cocotb.test()
async def test_identity_and_defaults(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off in (N, M, TICKS):
        await e.b.expect(off, e.m.read(off), "register")
    await e.b.cycles(50)
    assert not any(e.mon.v["tick"]), "ticks while disabled"


@cocotb.test()
async def test_even_spreading(dut):
    e = Env(dut)
    await e.start()
    for n, m in ((3, 8), (1, 7), (5, 12), (7, 10), (1, 1), (2, 3)):
        await e.check_pattern(n, m)


@cocotb.test()
async def test_clamping_rules(dut):
    e = Env(dut)
    await e.start()
    await e.check_pattern(9, 4)       # N > M: every clock
    await e.check_pattern(5, 0)       # M = 0 acts as 1
    await e.check_pattern(0, 6)       # no ticks at all


@cocotb.test()
async def test_counter_toggle_and_hold(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.setup(2, 5)
    mark = e.mon.mark()
    await e.burst(6)
    ticks = sum(e.mon.since("tick", mark))
    flips = e.mon.since("flip", mark)
    assert sum(1 for a, b in zip(flips, flips[1:]) if a != b) in (ticks, ticks - 1, ticks + 1), "LED[1] must toggle on every tick"
    assert await e.b.read(TICKS) == ticks, "TICKS != ticks seen on LED[0]"
    await e.b.cycles(200)                       # disabled: holds
    assert await e.b.read(TICKS) == ticks
    await e.b.write(CTRL, 0)
    await e.b.expect(TICKS, 0, "TICKS after clear")


@cocotb.test()
async def test_random_rates(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(4):
        m = rng.randrange(2, 30)
        await e.check_pattern(rng.randrange(0, m + 2), m)
