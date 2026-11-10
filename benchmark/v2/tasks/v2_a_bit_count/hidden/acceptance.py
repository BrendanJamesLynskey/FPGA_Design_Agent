"""Acceptance tests of v2_a_bit_count against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import DESIGN_ID, LZC, POP, REV, WORD, Model

NAMES = ("WORD", "POP", "LZC", "REV")


class Env:
    def __init__(self, dut) -> None:
        self.dut, self.b, self.m = dut, Board(dut, {}), Model()

    async def word(self, v: int) -> None:
        await self.b.write(WORD, v)
        self.m.write(WORD, v)

    async def check(self, offs=(POP, LZC, REV), led: bool = True) -> None:
        for off in offs:
            await self.b.expect(off, self.m.read(off), f"{NAMES[off]} of {self.m.w:#010x}")
        if led:
            got = await peek(self.b.clk, self.dut.LED)
            assert got == self.m.leds(), f"LED {got:04X}, model {self.m.leds():04X} for {self.m.w:#010x}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.b.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check((WORD, POP, LZC, REV))
    await e.word(0xDEADBEEF)
    await e.b.reset()
    e.m = Model()
    await e.check((WORD, POP, LZC, REV))


@cocotb.test()
async def test_zero_word(dut):
    """A zero word has no 1 bit: POP 0, LZC 32."""
    e = Env(dut)
    await e.b.start()
    await e.word(0x1)
    await e.word(0)
    await e.check()
    await e.b.expect(LZC, 32, "LZC of zero")


@cocotb.test()
async def test_one_hot_words(dut):
    e = Env(dut)
    await e.b.start()
    for n in range(32):
        await e.word(1 << n)
        await e.check()


@cocotb.test()
async def test_dense_words(dut):
    e = Env(dut)
    await e.b.start()
    for w in (0xFFFFFFFF, 0xFFFFFFFE, 0x7FFFFFFF, 0x55555555, 0xAAAAAAAA, 0x0000FFFF, 0xFFFF0000, 0x12345678,
              0x80000001, 0xF0F0F0F0):
        await e.word(w)
        await e.check()


@cocotb.test()
async def test_random_words(dut):
    e = Env(dut)
    await e.b.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(16):
        w = rng.getrandbits(32) >> rng.randrange(32) << rng.randrange(8)
        await e.word(w & 0xFFFFFFFF)
        await e.check()


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.b.start()
    await e.word(0xCAFEF00D)
    for off, junk in ((POP, 0x3F), (LZC, 0), (REV, 0x12345678)):
        await e.b.write(off, junk)                # read-only
    await e.check((WORD, POP, LZC, REV))
    for off in (0x04, 0x40, 0x7F):
        await e.b.expect(off, 0, "unmapped")
