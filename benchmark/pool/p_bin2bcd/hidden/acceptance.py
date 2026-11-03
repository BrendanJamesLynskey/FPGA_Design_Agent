"""Acceptance tests of p_bin2bcd against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek, scan_display
from model import BCD, DESIGN_ID, IN, STATUS, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {})
        self.m = Model()
        self.slot = 1 << self.b.param("REFRESH_BITS")

    async def start(self) -> None:
        await self.b.start()

    async def put(self, v: int) -> None:
        await self.b.write(IN, v)
        self.m.write(IN, v)
        await self.b.cycles(60)

    async def check(self, display: bool = True) -> None:
        for off, name in ((IN, "IN"), (BCD, "BCD"), (STATUS, "STATUS")):
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"
        if display:
            seen = await scan_display(self.dut, self.b.clk, self.slot)
            want = self.m.display()
            assert {k: v[0] for k, v in seen.items()} == want, f"display {seen} != model {want}"
            assert all(v[1] == 1 for v in seen.values()), "DP lit"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check()


@cocotb.test()
async def test_conversions(dut):
    e = Env(dut)
    await e.start()
    for v in (7, 10, 99, 100, 4095, 65535, 65536, 99999, 12345):
        await e.put(v)
        await e.check()


@cocotb.test()
async def test_overflow_clamps_magnitude_only(dut):
    e = Env(dut)
    await e.start()
    for v in (100000, 131071, 1 << 31 | 100000, 1 << 31 | 99999):
        await e.put(v)
        await e.check()
    assert e.m.ovf or e.m.neg


@cocotb.test()
async def test_sign_and_negative_zero(dut):
    """A textbook converter shows -0 or drops the sign position: here the minus follows the first digit."""
    e = Env(dut)
    await e.start()
    for v in (1 << 31 | 5, 1 << 31 | 0, 1 << 31 | 10, 1 << 31 | 99999, 1 << 31 | 1 << 20 | 3):
        await e.put(v)
        await e.check()


@cocotb.test()
async def test_random_numbers(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(8):
        mag = rng.choice([rng.randrange(10), rng.randrange(1000), rng.randrange(100000), rng.randrange(131072)])
        await e.put(mag | (rng.randrange(2) << 31) | (rng.randrange(1 << 14) << 17 if rng.random() < 0.3 else 0))
        await e.check()
