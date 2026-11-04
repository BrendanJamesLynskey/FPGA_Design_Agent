"""Acceptance tests of p_adler32 against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import ADLER, BYTE, COUNT, CTRL, DESIGN_ID, WORD, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {})
        self.m = Model()

    async def start(self) -> None:
        await self.b.start()

    async def feed(self, data: bytes) -> None:
        i = 0
        while i < len(data):
            if len(data) - i >= 4 and (i // 4) % 2 == 0:
                v = int.from_bytes(data[i:i + 4], "little")
                await self.b.write(WORD, v)
                self.m.write(WORD, v)
                i += 4
            else:
                await self.b.write(BYTE, data[i])
                self.m.write(BYTE, data[i])
                i += 1

    async def check(self) -> None:
        await self.b.cycles(20)
        for off, name in ((ADLER, "ADLER"), (COUNT, "COUNT")):
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check()
    await e.b.expect(ADLER, 1, "ADLER after reset")


@cocotb.test()
async def test_wikipedia(dut):
    e = Env(dut)
    await e.start()
    await e.feed(b"Wikipedia")
    await e.check()
    assert await e.b.read(ADLER) == 0x11E60398


@cocotb.test()
async def test_word_order_and_byte_mix(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(WORD, 0x04030201)
    e.m.write(WORD, 0x04030201)
    await e.check()
    await e.b.write(BYTE, 0x1FF)            # only the low byte is used
    e.m.write(BYTE, 0x1FF)
    await e.b.write(WORD, 0xA0000000)
    e.m.write(WORD, 0xA0000000)
    await e.check()


@cocotb.test()
async def test_long_message_exceeds_modulus(dut):
    e = Env(dut)
    await e.start()
    await e.feed(b"\xff" * 280)             # A passes 65521 on the way
    await e.check()
    assert e.m.read(ADLER) & 0xFFFF != 1 + 280 * 255


@cocotb.test()
async def test_start_over_and_random(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    await e.feed(bytes(rng.randrange(256) for _ in range(23)))
    await e.check()
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.check()
    await e.feed(bytes(rng.randrange(256) for _ in range(11)))
    await e.check()
