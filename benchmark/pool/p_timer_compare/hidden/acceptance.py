"""Acceptance tests of p_timer_compare against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from benchmark.pool.poollib import Monitor
from model import CMPA, CMPB, CNT, CTRL, DESIGN_ID, FLAGS, PRESC, Model

RUN, ARL = 1, 2


def mode(a: int = 0, b: int = 0, init_a: int = 0, init_b: int = 0) -> int:
    return (a << 2) | (b << 4) | (init_a << 6) | (init_b << 7)


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {})
        self.m = Model()

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, a=lambda: int(self.dut.LED.value) & 1, b=lambda: (int(self.dut.LED.value) >> 1) & 1)

    async def w(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def check_regs(self) -> None:
        for off, name in ((CTRL, "CTRL"), (PRESC, "PRESC"), (CNT, "CNT"), (CMPA, "CMPA"), (CMPB, "CMPB"), (FLAGS, "FLAGS")):
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led & 3 == self.m.leds(), f"LED {led & 3:02b} != model {self.m.leds():02b}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_regs()


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.start()
    for off, v in ((PRESC, 12345), (CMPA, 0xDEADBEEF), (CMPB, 7), (CNT, 0x12345678)):
        await e.w(off, v)
    await e.check_regs()
    await e.w(CTRL, RUN)
    await e.w(CNT, 99)                          # ignored while running
    await e.w(CTRL, 0)
    await e.b.cycles(20)
    c = await e.b.read(CNT)
    assert c != 99, "CNT written while running"
    await e.w(CTRL, mode(0, 0, 1, 1))           # forced start levels
    await e.b.cycles(4)
    led = await peek(e.b.clk, dut.LED)
    assert led & 3 == 3


@cocotb.test()
async def test_autoreload_period_and_channel_offset(dut):
    e = Env(dut)
    await e.start()
    k, j, p = 9, 4, 2
    for off, v in ((PRESC, p), (CMPA, k), (CMPB, j), (CNT, 0)):
        await e.w(off, v)
    await e.w(CTRL, RUN | ARL | mode(3, 3))
    mark = e.mon.mark()
    await e.b.cycles(8 * (k + 1) * (p + 1))
    await e.w(CTRL, 0)
    ta = [i for i in range(1, len(e.mon.since("a", mark))) if e.mon.since("a", mark)[i] != e.mon.since("a", mark)[i - 1]]
    tb = [i for i in range(1, len(e.mon.since("b", mark))) if e.mon.since("b", mark)[i] != e.mon.since("b", mark)[i - 1]]
    per = (k + 1) * (p + 1)
    assert len(ta) >= 5 and len(tb) >= 5, (ta, tb)
    assert {y - x for x, y in zip(ta, ta[1:])} == {per}, f"A toggles {ta}, period should be {per}"
    assert {y - x for x, y in zip(tb, tb[1:])} == {per}, f"B toggles {tb}, period should be {per}"
    lead = (ta[1] - tb[1]) % per
    assert lead == (k - j) * (p + 1), f"B leads A by {lead} clocks, want {(k - j) * (p + 1)}"
    await e.b.expect(FLAGS, 3, "FLAGS")


@cocotb.test()
async def test_set_clear_and_flags(dut):
    e = Env(dut)
    await e.start()
    for off, v in ((PRESC, 3), (CMPA, 6), (CMPB, 3), (CNT, 0)):
        await e.w(off, v)
    await e.w(CTRL, RUN | mode(1, 2, 0, 1))      # A: set on match, B: clear on match, B starts high
    await e.b.cycles(80)                         # counts 1..6 last 4 clocks each
    led = int(dut.LED.value) & 3
    assert led == 0b01, f"LED[1:0] = {led:02b}: A set on match, B cleared on match"
    await e.b.expect(FLAGS, 3, "FLAGS")
    await e.b.write(FLAGS, 0)
    await e.b.expect(FLAGS, 0, "FLAGS after clear")
    await e.b.cycles(40)
    await e.b.expect(FLAGS, 0, "no new match while the counter is past the compares")
    await e.w(CTRL, 0)


@cocotb.test()
async def test_random_free_run_counts(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    p = rng.randrange(0, 4)
    await e.w(PRESC, p)
    await e.w(CNT, 0)
    await e.w(CTRL, RUN)
    await e.b.cycles(1000)
    await e.w(CTRL, 0)
    c = await e.b.read(CNT)
    assert 2000 // (p + 1) - 3 <= c <= 2400 // (p + 1) + 3, f"CNT {c} after about 2200 clocks of free run at PRESC {p}"
