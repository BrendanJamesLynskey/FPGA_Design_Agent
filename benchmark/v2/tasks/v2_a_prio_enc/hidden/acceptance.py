"""Acceptance tests of v2_a_prio_enc against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge
from model import DESIGN_ID, LATENCY, MASK, REQ, WINNER, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut, self.b, self.m = dut, Board(dut, {"SW": 0}), Model()

    async def wr_mask(self, v: int) -> None:
        await self.b.write(MASK, v)
        self.m.write(MASK, v)

    async def set_sw(self, v: int) -> None:
        self.dut.SW.value = v
        self.m.req = v
        await self.b.cycles(LATENCY + 3)

    async def check(self) -> None:
        what = f"SW={self.m.req:#06x} mask={self.m.mask:#06x}"
        got = await peek(self.b.clk, self.dut.LED)
        assert got == self.m.grant(), f"LED {got:#06x}, model {self.m.grant():#06x} ({what})"
        await self.b.expect(WINNER, self.m.read(WINNER), "WINNER " + what)

    async def led_latency(self, v: int) -> int:
        """Clocks from driving SW to LED showing the winner."""
        await FallingEdge(self.b.clk)
        self.dut.SW.value = v
        self.m.req = v
        for n in range(1, 12):
            await RisingEdge(self.b.clk)
            await ReadOnly()
            if int(self.dut.LED.value) == self.m.grant():
                return n
            await FallingEdge(self.b.clk)
        return 99


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.b.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off in (REQ, MASK, WINNER):
        await e.b.expect(off, e.m.read(off), "register")
    assert int(dut.LED.value) == 0
    await e.wr_mask(0x00F0)
    await e.b.reset()
    e.m = Model()
    await e.b.expect(MASK, 0, "MASK after reset")
    await e.b.expect(WINNER, 0x0F, "WINNER after reset")


@cocotb.test()
async def test_single_requests(dut):
    e = Env(dut)
    await e.b.start()
    for n in range(16):
        await e.set_sw(1 << n)
        await e.check()
    await e.set_sw(0)
    await e.check()
    await e.b.expect(WINNER, 0x0F, "no request")


@cocotb.test()
async def test_highest_wins(dut):
    e = Env(dut)
    await e.b.start()
    for v in (0x0003, 0x8001, 0xFFFF, 0x00F0, 0x5555, 0xAAAA, 0x0101, 0x7FFF, 0x0006, 0xC000):
        await e.set_sw(v)
        await e.check()


@cocotb.test()
async def test_mask(dut):
    e = Env(dut)
    await e.b.start()
    await e.set_sw(0xFFFF)
    for mk in (0x8000, 0xC000, 0xFF00, 0x00FF, 0xFFFE, 0xFFFF, 0x5555):
        await e.wr_mask(mk)
        await e.check()
    await e.set_sw(0x0F0F)
    for mk in (0x0F00, 0x0F0F, 0x0001, 0xF0F0):
        await e.wr_mask(mk)
        await e.check()
    await e.b.expect(REQ, 0x0F0F, "REQ is the raw switches")


@cocotb.test()
async def test_led_latency_and_random(dut):
    e = Env(dut)
    await e.b.start()
    n = await e.led_latency(0x0400)
    assert n == LATENCY, f"LED followed the switch after {n} clocks, want {LATENCY}"
    await e.b.cycles(5)
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(16):
        if rng.random() < 0.3:
            await e.wr_mask(rng.getrandbits(16) & rng.getrandbits(16))
        await e.set_sw(rng.getrandbits(16) & rng.getrandbits(16))
        await e.check()


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.b.start()
    await e.wr_mask(0xABCD_0001)                  # only [15:0]
    await e.b.expect(MASK, 0x0001, "MASK")
    await e.set_sw(0x0003)
    await e.b.write(WINNER, 5)
    await e.b.write(REQ, 5)
    await e.check()
    for off in (0x03, 0x40, 0x7F):
        await e.b.expect(off, 0, "unmapped")
