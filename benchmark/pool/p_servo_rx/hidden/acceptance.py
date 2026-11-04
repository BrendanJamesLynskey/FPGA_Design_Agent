"""Acceptance tests of p_servo_rx against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import BAD, CTRL, DESIGN_ID, GOOD, POS, STATUS, WIDTH, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"JA1": 0})
        p = self.b.param
        self.m = Model(p("MIN_W"), p("MAX_W"), p("VALID_MIN"), p("VALID_MAX"))
        self.fs = p("FAILSAFE_CYCLES")

    async def start(self) -> None:
        await self.b.start()

    async def pulse(self, w: int, gap: int = 300) -> None:
        self.dut.JA1.value = 1
        await self.b.cycles(w)
        self.dut.JA1.value = 0
        await self.b.cycles(gap)
        self.m.pulse(w)

    async def check(self, led: bool = True) -> None:
        for off, name in ((WIDTH, "WIDTH"), (POS, "POS"), (STATUS, "STATUS")):
            await self.b.expect(off, self.m.read(off), name)
        if led:
            v = await peek(self.b.clk, self.dut.LED)
            assert v == self.m.leds(), f"LED {v:04X} != model {self.m.leds():04X}"

    async def counts(self) -> None:
        for off, name in ((GOOD, "GOOD"), (BAD, "BAD")):
            await self.b.expect(off, self.m.read(off), name)

    async def expire(self) -> None:
        await self.b.cycles(self.fs + 800)
        self.m.timeout()


@cocotb.test()
async def test_identity_and_neutral_start(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.b.expect(POS, 128, "POS at reset")
    await e.b.expect(STATUS, 0, "STATUS at reset")


@cocotb.test()
async def test_width_to_position_mapping(dut):
    e = Env(dut)
    await e.start()
    for w in (150, 100, 200, 120, 101, 199, 80, 220, 175):
        await e.pulse(w)
        await e.check()
    await e.counts()


@cocotb.test()
async def test_bad_pulses_ignored(dut):
    e = Env(dut)
    await e.start()
    await e.pulse(140)
    for w in (60, 79, 221, 400):
        await e.pulse(w)
        await e.check()
        await e.pulse(140)                         # bad pulses do not restart the failsafe timer: refresh it
    await e.counts()
    assert e.m.bad == 4 and e.m.stored == e.m.position(140)
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.counts()


@cocotb.test()
async def test_failsafe_and_recovery(dut):
    e = Env(dut)
    await e.start()
    await e.pulse(180)
    await e.check()
    await e.expire()
    await e.check()                                # position 128, FAIL set, width kept
    assert e.m.fail
    await e.pulse(70)                              # a bad pulse does not end the failsafe
    await e.check()
    assert e.m.fail
    await e.pulse(190)
    await e.check()
    assert not e.m.fail and e.m.pos == e.m.position(190)


@cocotb.test()
async def test_random_pulses(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(8):
        await e.pulse(rng.choice([rng.randrange(60, 240), rng.randrange(100, 201)]), gap=rng.randrange(50, 600))
    await e.check()
    await e.counts()
