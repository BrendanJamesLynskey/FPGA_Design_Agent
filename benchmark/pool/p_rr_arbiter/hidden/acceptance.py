"""Acceptance tests of p_rr_arbiter against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor, align, runs, script
from model import DESIGN_ID, FORCED, GRANTS0, LAST, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        self.hold = self.b.param("MAX_HOLD")
        self.m = Model(self.hold)

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, sw=lambda: int(self.dut.SW.value) & 15, g=lambda: int(self.dut.LED.value) & 15)

    async def play(self, steps) -> None:
        """Drive SW[3:0] through (value, clocks) steps, then compare the grant trace with the model clock by clock."""
        await script(self.dut, "SW", steps, self.b.clk)
        await self.b.cycles(8)
        sws = self.mon.v["sw"]
        out = Model(self.hold)
        self.m = out
        trace = out.run(sws)
        align(self.mon.v["g"], trace, 4, "grant lines")
        self.last_trace = self.mon.v["g"]

    async def check_regs(self) -> None:
        await self.b.cycles(4)
        for off in range(GRANTS0, LAST + 1):
            await self.b.expect(off, self.m.read(off), ("GRANTS0", "GRANTS1", "GRANTS2", "GRANTS3", "FORCED", "LAST")[off])


@cocotb.test()
async def test_identity_and_idle(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.play([(0, 30)])
    await e.check_regs()


@cocotb.test()
async def test_everyone_requests_rotation(dut):
    e = Env(dut)
    await e.start()
    await e.play([(0xF, 10 * e.hold), (0, 20)])
    r = [(v, n) for v, _, n in runs(e.last_trace)][1:-1]
    grants = [v for v, n in r if v]
    assert grants[:6] == [1, 2, 4, 8, 1, 2], grants
    assert all(n == e.hold for v, n in r if v), f"grant lengths {[n for v, n in r if v]}, want {e.hold}"
    assert all(n == 1 for v, n in r if not v and n < 5), "grants must be one clock apart"
    await e.check_regs()


@cocotb.test()
async def test_hold_until_someone_waits(dut):
    e = Env(dut)
    await e.start()
    await e.play([(0b0100, 6 * e.hold), (0b0101, 4), (0b0001, 2 * e.hold), (0, 20)])
    await e.check_regs()
    assert e.m.forced == 1 and e.m.last == 0


@cocotb.test()
async def test_next_in_rotation_after_release(dut):
    e = Env(dut)
    await e.start()
    await e.play([(0b0010, 20), (0b1101, 20), (0b1001, 20), (0b1000, 20), (0, 20)])
    await e.check_regs()
    assert e.m.grants[2] == 1 and e.m.grants[3] == 1 and e.m.grants[0] == 1 and e.m.grants[1] == 1
    await e.b.write(GRANTS0, 1)
    e.m.write(GRANTS0, 1)
    await e.check_regs()


@cocotb.test()
async def test_random_requests(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    steps = [(rng.randrange(16), rng.choice([1, 2, 3, 5, 9, 14, 25, 40])) for _ in range(60)]
    await e.play(steps + [(0, 30)])
    await e.check_regs()
