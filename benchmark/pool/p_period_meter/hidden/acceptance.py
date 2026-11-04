"""Acceptance tests of p_period_meter against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import COUNT, CTRL, DESIGN_ID, LAST, MAX, MIN, STALLED, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        self.timeout = self.b.param("TIMEOUT_PERIOD")
        self.m = Model(self.timeout)
        self.first = True

    async def start(self) -> None:
        await self.b.start()

    async def edges(self, spacings, first: bool = False) -> None:
        """Raise SW[0] now and again after each spacing (clocks between consecutive rising edges)."""
        todo = [None] + list(spacings) if (self.first or first) else list(spacings)
        for d in todo:
            if d is not None:
                self.dut.SW.value = 0
                await self.b.cycles(d - 3)
            self.dut.SW.value = 1
            await self.b.cycles(3)
            if d is not None:
                if d > self.timeout:
                    self.m.timed_out()
                self.m.edge(d)
            else:
                self.m.edge(None)
        self.first = False
        self.dut.SW.value = 0
        await self.b.cycles(4)

    async def check(self) -> None:
        for off, name in ((LAST, "LAST"), (MIN, "MIN"), (MAX, "MAX"), (COUNT, "COUNT"), (STALLED, "STALLED")):
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
async def test_exact_periods(dut):
    e = Env(dut)
    await e.start()
    await e.edges([100, 37, 250, 100, 9])
    await e.check()
    assert e.m.min == 9 and e.m.max == 250 and e.m.count == 5


@cocotb.test()
async def test_stall_and_recovery(dut):
    e = Env(dut)
    await e.start()
    await e.edges([80, 90])
    await e.check()
    dut.SW.value = 0
    await e.b.cycles(e.timeout + 400)           # edges stop
    e.m.timed_out()
    await e.b.expect(STALLED, 1, "STALLED")
    await e.b.expect(LAST, 90, "LAST kept while stalled")
    await e.edges([], first=True)               # the first edge back restarts only
    await e.check()
    assert e.m.count == 2 and not e.m.stalled
    await e.edges([55])
    await e.check()
    assert e.m.count == 3 and e.m.last == 55


@cocotb.test()
async def test_clear_and_led_saturation(dut):
    e = Env(dut)
    await e.start()
    await e.edges([60, 40])
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.check()
    await e.edges([70, 30])                     # the first edge after the clear only restarts
    await e.check()
    assert e.m.count == 1 and e.m.last == 30


@cocotb.test()
async def test_random_spacings(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    await e.edges([rng.randrange(5, 2500) for _ in range(8)])
    await e.check()
