"""Acceptance tests of t1_sync_fifo_regs against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import AF_THRESH, DESIGN_ID, FLAGS, HEAD, LEVEL, POP, PUSH, Model


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, {})
        self.dut, self.m = dut, Model()

    async def start(self) -> None:
        await self.b.start()

    async def push(self, v: int) -> None:
        await self.b.write(PUSH, v)
        self.m.push(v)

    async def pop(self) -> None:
        want = self.m.pop()
        await self.b.expect(POP, want, "POP")

    async def wr(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def check_regs(self) -> None:
        for off, name in ((HEAD, "HEAD"), (LEVEL, "LEVEL"), (FLAGS, "FLAGS"), (AF_THRESH, "AF_THRESH"),
                          (PUSH, "PUSH")):
            await self.b.expect(off, self.m.read(off), name)

    async def check_leds(self) -> None:
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_fwft_head_and_pop(dut):
    """Trap: a FIFO Generator in standard (non-FWFT) read mode shows a byte one read late; HEAD and POP here must
    return the head byte at once."""
    e = Env(dut)
    await e.start()
    await e.push(0xA1)
    await e.b.expect(HEAD, 0xA1, "HEAD right after the first push")
    await e.push(0xB2)
    await e.push(0xC3)
    await e.b.expect(HEAD, 0xA1, "HEAD")
    await e.pop()                               # A1
    await e.b.expect(HEAD, 0xB2, "HEAD after one pop")
    await e.b.expect(HEAD, 0xB2, "HEAD read twice removes nothing")
    await e.pop()                               # B2
    await e.pop()                               # C3
    await e.pop()                               # empty: 0, UNDERFLOW
    await e.check_regs()


@cocotb.test()
async def test_fill_and_overflow(dut):
    e = Env(dut)
    await e.start()
    for i in range(16):
        await e.push(0x40 + i)
        if i in (0, 7, 11, 15):
            await e.check_regs()
            await e.check_leds()
    await e.push(0xEE)                          # dropped: OVERFLOW
    await e.push(0xEF)
    await e.check_regs()
    await e.check_leds()
    for _ in range(16):
        await e.pop()
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_underflow_and_w1c(dut):
    e = Env(dut)
    await e.start()
    await e.b.expect(HEAD, 0, "HEAD when empty")
    await e.check_regs()                        # a HEAD read when empty is not an underflow
    await e.pop()                               # UNDERFLOW
    for _ in range(17):
        await e.push(7)                         # OVERFLOW too
    await e.check_regs()
    await e.wr(FLAGS, 0)                        # 0 bits clear nothing
    await e.check_regs()
    await e.wr(FLAGS, 1 << 8)                   # clears only OVERFLOW
    await e.check_regs()
    await e.wr(FLAGS, 0x07)                     # read-only bits: ignored
    await e.check_regs()
    await e.wr(FLAGS, 1 << 9)
    await e.check_regs()
    await e.pop()
    await e.wr(FLAGS, 0x300)
    await e.check_regs()


@cocotb.test()
async def test_almost_full_threshold(dut):
    e = Env(dut)
    await e.start()
    for th in (0, 1, 5, 16, 17, 31, 12):
        await e.wr(AF_THRESH, th)
        await e.check_regs()
    for i in range(16):                         # walk the level with the threshold at 12, then 4
        await e.push(i)
        await e.b.expect(FLAGS, e.m.read(FLAGS), "FLAGS")
    await e.wr(AF_THRESH, 4)
    for _ in range(14):
        await e.pop()
        await e.b.expect(FLAGS, e.m.read(FLAGS), "FLAGS")


@cocotb.test()
async def test_pointer_wrap_order(dut):
    e = Env(dut)
    await e.start()
    n = 0
    for _ in range(7):                          # level hovers 3..8 while the pointers wrap several times
        for _ in range(8):
            await e.push(n & 0xFF)
            n += 5
        for _ in range(5):
            await e.pop()
        await e.b.expect(LEVEL, e.m.read(LEVEL), "LEVEL")
        await e.b.expect(HEAD, e.m.read(HEAD), "HEAD")
        if len(e.m.q) > 8:
            for _ in range(len(e.m.q) - 3):
                await e.pop()
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_leds_thermometer(dut):
    e = Env(dut)
    await e.start()
    for i in range(16):
        await e.push(i)
        await e.check_leds()
    for _ in range(16):
        await e.pop()
        await e.check_leds()


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.start()
    await e.push(0x1_2345_6789)                 # only [7:0] stored
    await e.b.write(POP, 0x55)                  # writes to RO registers are ignored (no pop, no push)
    await e.b.write(HEAD, 0x66)
    await e.b.write(LEVEL, 3)
    await e.wr(AF_THRESH, 0xFFFF_FFE3)          # [4:0] only
    await e.check_regs()
    for off in (0x06, 0x41, 0x7F):
        await e.b.expect(off, 0, "unmapped")
    await e.pop()
    await e.check_regs()


@cocotb.test()
async def test_random_traffic(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(70):
        r = rng.random()
        bias = 0.6 if len(e.m.q) < 8 else 0.4
        if r < 0.05:
            await e.wr(AF_THRESH, rng.randrange(32))
        elif r < 0.1:
            await e.wr(FLAGS, rng.choice((0x100, 0x200, 0x300)))
        elif r < 0.1 + bias:
            await e.push(rng.getrandbits(8))
        else:
            await e.pop()
        if rng.random() < 0.15:
            await e.b.expect(FLAGS, e.m.read(FLAGS), "FLAGS")
    await e.check_regs()
    await e.check_leds()
