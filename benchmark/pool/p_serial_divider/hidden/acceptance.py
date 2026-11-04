"""Acceptance tests of p_serial_divider against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import CTRL, DEN, DESIGN_ID, NUM, QUOT, REM, STATUS, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {})
        self.m = Model()

    async def start(self) -> None:
        await self.b.start()

    async def divide(self, a: int, d: int) -> None:
        for off, v in ((NUM, a), (DEN, d), (CTRL, 1)):
            await self.b.write(off, v)
            self.m.write(off, v)
        await self.b.cycles(40)
        await self.check()

    async def check(self) -> None:
        for off, name in ((QUOT, "QUOT"), (REM, "REM"), (STATUS, "STATUS")):
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check()
    await e.b.expect(NUM, 0, "NUM")
    await e.b.expect(DEN, 0, "DEN")


@cocotb.test()
async def test_ordinary_divisions(dut):
    e = Env(dut)
    await e.start()
    for a, d in ((1000, 7), (65535, 1), (65535, 65535), (12345, 100), (255, 16), (32768, 3)):
        await e.divide(a, d)
        assert e.m.read(STATUS) >> 8 == 17


@cocotb.test()
async def test_quick_cases(dut):
    e = Env(dut)
    await e.start()
    await e.divide(1234, 0)               # division by zero does not hang and reports 1 clock
    assert e.m.divz and e.m.cycles == 1
    await e.divide(5, 9)                  # divisor larger: 2 clocks
    assert e.m.cycles == 2
    await e.divide(0, 5)
    assert e.m.cycles == 2
    await e.divide(0, 0)
    await e.divide(7, 7)                  # equal operands take the full 17
    assert e.m.cycles == 17


@cocotb.test()
async def test_operand_registers_and_restart(dut):
    e = Env(dut)
    await e.start()
    await e.divide(9999, 10)
    await e.b.expect(NUM, 9999, "NUM")
    await e.b.expect(DEN, 10, "DEN")
    await e.b.write(NUM, 0x1FFFF)         # 16-bit operand: upper bit dropped
    e.m.write(NUM, 0x1FFFF)
    await e.b.write(CTRL, 0)              # bit 0 clear: no start
    e.m.write(CTRL, 0)
    await e.b.cycles(30)
    await e.check()
    await e.b.write(CTRL, 3)
    e.m.write(CTRL, 3)
    await e.b.cycles(40)
    await e.check()


@cocotb.test()
async def test_random_divisions(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(12):
        a = rng.choice([rng.randrange(65536), rng.randrange(256), 65535 - rng.randrange(4)])
        d = rng.choice([rng.randrange(65536), rng.randrange(1, 300), 0 if rng.random() < 0.2 else rng.randrange(1, 9)])
        await e.divide(a, d)
