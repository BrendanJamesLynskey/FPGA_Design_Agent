"""Acceptance tests of p_sat_accum against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import ACC, ADDS, DESIGN_ID, FLAGS, LIMIT, Model

FREEZE, CLEAR = 0x8000, 0x4000


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": FREEZE})          # frozen from reset: ADDS stays 0
        self.m = Model(self.b.param("SAT_LIMIT"))
        self.per = self.b.param("ACC_PERIOD")

    async def start(self) -> None:
        await self.b.start()

    async def sw(self, v: int) -> None:
        self.dut.SW.value = v
        await self.b.cycles(6)

    async def run_adds(self, v: int, periods: int) -> int:
        """Let the adds run for about `periods` ticks with value v, freeze, and replay them in the model."""
        before = self.m.adds
        await self.sw(v & 0xFF)
        await self.b.cycles(periods * self.per + self.per // 2)
        await self.sw((v & 0xFF) | FREEZE)
        k = (await self.b.read(ADDS) - before) & 0xFFFF
        assert abs(k - periods) <= 1, f"{k} adds in {periods} periods"
        for _ in range(k):
            self.m.tick(v)
        return k

    async def check(self) -> None:
        for off, name in ((ACC, "ACC"), (FLAGS, "FLAGS"), (ADDS, "ADDS"), (LIMIT, "LIMIT")):
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
async def test_saturate_high_exact_landing(dut):
    e = Env(dut)
    await e.start()
    await e.run_adds(100, 8)                  # 800
    await e.check()
    await e.run_adds(100, 3)                  # reaches 1000 exactly, then clamps
    await e.check()
    assert e.m.hi and e.m.acc == e.m.limit


@cocotb.test()
async def test_saturate_low_and_flags_clear(dut):
    e = Env(dut)
    await e.start()
    await e.run_adds(0xC0, 20)                # -64 each
    await e.check()
    assert e.m.lo and e.m.acc == -e.m.limit
    await e.b.write(FLAGS, 3)
    e.m.write(FLAGS, 3)
    await e.check()
    await e.run_adds(5, 4)                    # moves off the bottom: no new flag
    await e.check()


@cocotb.test()
async def test_clear_beats_freeze(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(ACC, 700)
    e.m.write(ACC, 700)
    await e.b.write(ACC, 5000)                # clamped write
    e.m.write(ACC, 5000)
    await e.check()
    await e.sw(CLEAR | FREEZE | 7)
    e.m.clear_level()
    await e.check()
    await e.b.cycles(3 * e.per)               # ticks while cleared neither add nor count
    await e.check()
    await e.sw(FREEZE)
    await e.run_adds(3, 3)
    await e.check()


@cocotb.test()
async def test_register_writes(dut):
    e = Env(dut)
    await e.start()
    for v in (0x1234, 0xFC00, 0x03E8, 0x0001):
        await e.b.write(ACC, v)
        e.m.write(ACC, v)
        await e.check()
    await e.b.write(ADDS, 77)
    e.m.write(ADDS, 77)
    await e.b.write(LIMIT, 5)
    await e.check()


@cocotb.test()
async def test_random(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(8):
        r = rng.random()
        if r < 0.25:
            v = rng.choice([0, 1, 0x7F, 0x80, 0xFF, rng.randrange(256)])
            await e.b.write(ACC, v * 5)
            e.m.write(ACC, v * 5)
        else:
            await e.run_adds(rng.randrange(256), rng.randrange(2, 7))
    await e.check()
