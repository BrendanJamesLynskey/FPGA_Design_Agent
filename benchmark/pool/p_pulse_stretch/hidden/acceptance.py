"""Acceptance tests of p_pulse_stretch against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor, high_runs, now_clk, same
from model import DESIGN_ID, HOLD, LONGEST, RETRIGS, TRIGGERS, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        self.m = Model(self.b.param("HOLD_CYCLES"))
        self.hold = self.m.hold

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, led0=lambda: int(self.dut.LED.value) & 1,
                           led1=lambda: (int(self.dut.LED.value) >> 1) & 1)
        self.mark = self.mon.mark()

    async def trig(self) -> int:
        t = now_clk()
        self.dut.SW.value = 1
        await self.b.cycles(4)
        self.dut.SW.value = 0
        self.m.trigger(t)
        return t

    async def finish(self) -> None:
        await self.b.cycles(self.hold + 40)

    def check_runs(self) -> None:
        got = [n for _, n in high_runs(self.mon.since("led0", self.mark))]
        same(got, self.m.run_lengths(), "lit run lengths in clocks")

    async def check_regs(self) -> None:
        for off, name in ((TRIGGERS, "TRIGGERS"), (RETRIGS, "RETRIGS"), (LONGEST, "LONGEST"), (HOLD, "HOLD")):
            await self.b.expect(off, self.m.read(off), name)


@cocotb.test()
async def test_identity_and_idle(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_regs()
    await e.b.cycles(20)
    assert max(e.mon.since("led0", e.mark)) == 0 and max(e.mon.since("led1", e.mark)) == 0


@cocotb.test()
async def test_lone_trigger_exact_length(dut):
    e = Env(dut)
    await e.start()
    await e.trig()
    await e.finish()
    e.check_runs()
    assert max(e.mon.since("led1", e.mark)) == 0, "LED[1] lit without a retrigger"
    await e.check_regs()


@cocotb.test()
async def test_retrigger_stretches_from_latest(dut):
    e = Env(dut)
    await e.start()
    await e.trig()
    await e.b.cycles(e.hold // 3)
    await e.trig()
    await e.b.cycles(e.hold // 4)
    assert (int(dut.LED.value) >> 1) & 1 == 1, "LED[1] should show the retrigger"
    await e.trig()                       # a third flip inside the stretched pulse
    await e.finish()
    e.check_runs()
    assert int(dut.LED.value) & 3 == 0
    await e.check_regs()


@cocotb.test()
async def test_separate_pulses_and_clear(dut):
    e = Env(dut)
    await e.start()
    await e.trig()
    await e.b.cycles(e.hold + 30)        # clearly after the end
    await e.trig()
    await e.finish()
    e.check_runs()
    await e.check_regs()
    await e.b.write(TRIGGERS, 0x1234)
    e.m.write(TRIGGERS, 0)
    await e.check_regs()


@cocotb.test()
async def test_random_flips(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(10):
        t = await e.trig()
        end = e.m.pulses[-1][1]
        gap = rng.choice([rng.randrange(8, e.hold - 8), rng.randrange(e.hold + 8, 2 * e.hold)])
        # keep clear of the unspecified window around the end of the lit time
        nxt = t + 4 + gap
        if abs(nxt - end) <= 6:
            gap += 12
        await e.b.cycles(gap)
    await e.finish()
    e.check_runs()
    await e.check_regs()
