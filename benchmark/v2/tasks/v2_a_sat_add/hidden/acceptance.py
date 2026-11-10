"""Acceptance tests of v2_a_sat_add against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import A, B, CTRL, DESIGN_ID, FLAGS, SUM, Model

PAIRS = [(0, 0), (1, 1), (0x7FFF, 1), (0x8000, 0xFFFF), (0x7FFF, 0x7FFF), (0x8000, 0x8000), (0xFFFF, 1),
         (0xFFFF, 0xFFFF), (0x4000, 0x4000), (0x8000, 0x7FFF), (0x1234, 0x0FF0), (0x0005, 0xFFFB)]


class Env:
    def __init__(self, dut) -> None:
        self.dut, self.b, self.m = dut, Board(dut, {}), Model()

    async def wr(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def check(self, led: bool = True) -> None:
        s, f = self.m.result()
        what = f"A={self.m.a:#06x} B={self.m.b:#06x} signed={self.m.signed} sat={self.m.sat}"
        await self.b.expect(SUM, s, "SUM " + what)
        await self.b.expect(FLAGS, f, "FLAGS " + what)
        if led:
            got = await peek(self.b.clk, self.dut.LED)
            assert got == s, f"LED {got:04X}, model SUM {s:04X} ({what})"

    async def sweep(self, pairs, modes=((0, 0), (0, 1), (1, 0), (1, 1))) -> None:
        for a, b in pairs:
            await self.wr(A, a)
            await self.wr(B, b)
            for sg, st in modes:
                await self.wr(CTRL, sg | st << 1)
                await self.check()


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.b.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off in range(5):
        await e.b.expect(off, e.m.read(off), "register")
    await e.wr(A, 0xFFFF)
    await e.wr(B, 3)
    await e.wr(CTRL, 3)
    await e.b.reset()
    e.m = Model()
    for off in range(5):
        await e.b.expect(off, e.m.read(off), "register after reset")


@cocotb.test()
async def test_unsigned_wrap_and_saturate(dut):
    e = Env(dut)
    await e.b.start()
    await e.sweep(PAIRS, modes=((0, 0), (0, 1)))


@cocotb.test()
async def test_signed_overflow_flag(dut):
    """Signed mode, no saturation: OVF is signed overflow, not the carry out."""
    e = Env(dut)
    await e.b.start()
    await e.sweep(PAIRS, modes=((1, 0),))


@cocotb.test()
async def test_signed_saturation(dut):
    e = Env(dut)
    await e.b.start()
    await e.sweep(PAIRS, modes=((1, 1),))


@cocotb.test()
async def test_random_operands(dut):
    e = Env(dut)
    await e.b.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(10):
        edge = [0, 1, 0x7FFF, 0x8000, 0xFFFF, rng.getrandbits(16), rng.getrandbits(16)]
        await e.sweep([(rng.choice(edge), rng.choice(edge))], modes=[(rng.randrange(2), rng.randrange(2))])


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.b.start()
    await e.wr(A, 0xABCD_7FFF)                    # only [15:0]
    await e.wr(B, 0x1_0001)
    await e.wr(CTRL, 0xFFFF_FFFF)                 # only [1:0]
    await e.b.expect(CTRL, 3, "CTRL")
    await e.check()
    await e.b.write(SUM, 5)
    await e.b.write(FLAGS, 5)
    await e.check()
    for off in (0x05, 0x40, 0x7F):
        await e.b.expect(off, 0, "unmapped")
