"""Acceptance tests of v2_a_shifter against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import A, CTRL, DESIGN_ID, RES, Model

NAMES = ("A", "CTRL", "RES")


class Env:
    def __init__(self, dut) -> None:
        self.dut, self.b, self.m = dut, Board(dut, {}), Model()

    async def wr(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def op(self, mode: int, amt: int) -> None:
        await self.wr(CTRL, mode << 8 | amt)

    async def check(self, led: bool = True) -> None:
        await self.b.expect(RES, self.m.res(), f"RES (A={self.m.a:#010x} mode {self.m.mode} amt {self.m.amt})")
        if led:
            got = await peek(self.b.clk, self.dut.LED)
            assert got == self.m.leds(), f"LED {got:04X}, model {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.b.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off in range(3):
        await e.b.expect(off, 0, NAMES[off])
    await e.wr(A, 0xDEADBEEF)
    await e.op(3, 9)
    await e.b.reset()
    e.m = Model()
    for off in range(3):
        await e.b.expect(off, 0, NAMES[off])


@cocotb.test()
async def test_logical_shifts(dut):
    e = Env(dut)
    await e.b.start()
    for a in (0x80000001, 0x12345678):
        await e.wr(A, a)
        for mode in (0, 1):
            for amt in (0, 1, 4, 15, 16, 31, 32, 33, 47, 63):
                await e.op(mode, amt)
                await e.check()


@cocotb.test()
async def test_arithmetic_right_shift(dut):
    e = Env(dut)
    await e.b.start()
    for a in (0x80000001, 0xF0F0F0F0, 0x7FFFFFFF, 0x40000000):
        await e.wr(A, a)
        for amt in (0, 1, 3, 16, 30, 31, 32, 40, 63):
            await e.op(2, amt)
            await e.check()


@cocotb.test()
async def test_rotate_left(dut):
    e = Env(dut)
    await e.b.start()
    for a in (0x80000001, 0x12345678):
        await e.wr(A, a)
        for amt in (0, 1, 5, 16, 31, 32, 33, 37, 62, 63):
            await e.op(3, amt)
            await e.check()


@cocotb.test()
async def test_random_operations(dut):
    e = Env(dut)
    await e.b.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(14):
        await e.wr(A, rng.getrandbits(32))
        for _ in range(2):
            await e.op(rng.randrange(4), rng.randrange(64))
            await e.check(led=False)
    await e.check()


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.b.start()
    await e.wr(A, 0xFFFF_FFFF)
    await e.wr(CTRL, 0xFFFF_FFFF)                 # only AMT [5:0] and MODE [9:8] are kept
    await e.b.expect(CTRL, 0x33F, "CTRL")
    await e.check()
    await e.b.write(RES, 0x1234)                  # read-only
    await e.check()
    for off in (0x03, 0x40, 0x7F):
        await e.b.expect(off, 0, "unmapped")
