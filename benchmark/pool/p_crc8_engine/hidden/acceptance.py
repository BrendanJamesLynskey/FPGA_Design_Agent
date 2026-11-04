"""Acceptance tests of p_crc8_engine against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import COUNT, CRC, CTRL, DATA, DESIGN_ID, STATUS, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {})
        self.m = Model()
        self.busy = 8 * self.b.param("BIT_CLKS")

    async def start(self) -> None:
        await self.b.start()

    async def feed(self, v: int) -> None:
        await self.b.write(DATA, v)
        self.m.write(DATA, v)
        await self.b.cycles(self.busy + 100)
        self.m.finish()

    async def check(self, leds: bool = True) -> None:
        for off, name in ((DATA, "DATA"), (CRC, "CRC"), (COUNT, "COUNT"), (STATUS, "STATUS")):
            await self.b.expect(off, self.m.read(off), name)
        if leds:
            led = await peek(self.b.clk, self.dut.LED)
            assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check()


@cocotb.test()
async def test_check_string(dut):
    e = Env(dut)
    await e.start()
    for ch in b"123456789":
        await e.feed(ch)
    await e.check()
    assert await e.b.read(CRC) == 0x4B


@cocotb.test()
async def test_byte_offered_while_busy_is_dropped(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(DATA, 0x11)
    e.m.write(DATA, 0x11)
    await e.b.write(DATA, 0x22)               # the engine is still busy with 0x11
    e.m.write(DATA, 0x22)
    await e.b.write(CTRL, 1)                  # also ignored while busy
    e.m.write(CTRL, 1)
    await e.b.expect(STATUS, e.m.read(STATUS), "STATUS while busy")
    await e.b.expect(CRC, 0, "CRC before the byte time is over")
    await e.b.cycles(e.busy + 100)
    e.m.finish()
    await e.check()
    assert e.m.dropped == 1 and e.m.count == 1


@cocotb.test()
async def test_ctrl_restart_and_clear_dropped(dut):
    e = Env(dut)
    await e.start()
    await e.feed(0xA5)
    await e.b.write(DATA, 0x01)
    e.m.write(DATA, 0x01)
    await e.b.write(DATA, 0x02)
    e.m.write(DATA, 0x02)
    await e.b.cycles(e.busy + 100)
    e.m.finish()
    await e.check()
    await e.b.write(CTRL, 2)
    e.m.write(CTRL, 2)
    await e.check()
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.check()


@cocotb.test()
async def test_random_messages(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(3):
        for _ in range(rng.randrange(2, 5)):
            await e.feed(rng.randrange(256))
        await e.check(leds=False)
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.feed(0xFF)
    await e.feed(0x00)
    await e.check()
