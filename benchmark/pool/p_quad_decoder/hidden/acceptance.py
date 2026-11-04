"""Acceptance tests of p_quad_decoder against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import DESIGN_ID, DIR, ERRS, FWD, POS, REV, Model

CYCLE = (0b00, 0b01, 0b11, 0b10)


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        self.m = Model(0)
        self.ab = 0
        self.index = 0

    async def start(self) -> None:
        await self.b.start()

    async def drive(self, ab: int | None = None, index: int | None = None) -> None:
        if ab is not None:
            self.m.set_ab(ab)
            self.ab = ab
        if index is not None:
            if index and not self.index:
                self.m.index()
            self.index = index
        self.dut.SW.value = self.ab | (self.index << 2)
        await self.b.cycles(6)

    async def walk(self, n: int, forward: bool = True) -> None:
        for _ in range(n):
            g = CYCLE.index(self.ab)
            await self.drive(CYCLE[(g + (1 if forward else -1)) % 4])

    async def check(self) -> None:
        for off, name in ((POS, "POS"), (FWD, "FWD"), (REV, "REV"), (ERRS, "ERRS"), (DIR, "DIR")):
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
async def test_forward_backward(dut):
    e = Env(dut)
    await e.start()
    await e.walk(10)
    await e.check()
    await e.walk(13, forward=False)
    await e.check()
    assert e.m.pos == 0xFFFD


@cocotb.test()
async def test_double_flip_is_an_error(dut):
    e = Env(dut)
    await e.start()
    await e.walk(3)
    await e.drive(ab=CYCLE[(CYCLE.index(e.ab) + 2) % 4])      # both channels at once
    await e.drive(ab=CYCLE[(CYCLE.index(e.ab) + 2) % 4])
    await e.check()
    assert e.m.errs == 2


@cocotb.test()
async def test_index_and_registers(dut):
    e = Env(dut)
    await e.start()
    await e.walk(5)
    await e.drive(index=1)
    await e.check()
    await e.walk(2, forward=False)
    await e.drive(index=0)
    await e.drive(index=1)
    await e.check()
    await e.b.write(POS, 0x7FFE)
    e.m.write(POS, 0x7FFE)
    await e.drive(index=0)
    await e.walk(3)
    await e.check()
    for off in (FWD, REV, ERRS):
        await e.b.write(off, 9)
        e.m.write(off, 9)
    await e.check()


@cocotb.test()
async def test_random_walk(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(40):
        r = rng.random()
        if r < 0.1:
            await e.drive(ab=CYCLE[(CYCLE.index(e.ab) + 2) % 4])
        elif r < 0.15:
            await e.drive(index=1 - e.index)
        else:
            await e.walk(1, forward=rng.random() < 0.6)
    await e.check()
