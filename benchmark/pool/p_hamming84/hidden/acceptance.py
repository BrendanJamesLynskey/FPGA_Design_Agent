"""Acceptance tests of p_hamming84 against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import DEC_IN, DEC_OUT, DESIGN_ID, ENC_IN, ENC_OUT, STATS, Model, encode


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {})
        self.m = Model()

    async def start(self) -> None:
        await self.b.start()

    async def enc(self, d: int) -> None:
        await self.b.write(ENC_IN, d)
        self.m.write(ENC_IN, d)
        await self.b.expect(ENC_OUT, self.m.read(ENC_OUT), f"ENC_OUT for {d:#x}")

    async def dec(self, r: int) -> None:
        await self.b.write(DEC_IN, r)
        self.m.write(DEC_IN, r)
        await self.b.expect(DEC_OUT, self.m.read(DEC_OUT), f"DEC_OUT for {r:#04x}")

    async def check_leds(self) -> None:
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off in range(5):
        await e.b.expect(off, e.m.read(off), "register")
    await e.check_leds()


@cocotb.test()
async def test_encoder_all_nibbles(dut):
    e = Env(dut)
    await e.start()
    for d in range(16):
        await e.enc(d)
    await e.enc(0x3A)                       # upper bits ignored
    await e.check_leds()


@cocotb.test()
async def test_single_errors_corrected(dut):
    e = Env(dut)
    await e.start()
    for d in (0x0, 0x9, 0xF):
        w = encode(d)
        await e.dec(w)
        for bit in range(8):
            await e.dec(w ^ (1 << bit))
    await e.b.expect(STATS, e.m.read(STATS), "STATS")
    await e.check_leds()


@cocotb.test()
async def test_double_errors_pass_data_through(dut):
    e = Env(dut)
    await e.start()
    w = encode(0xA)
    for a, b in ((0, 1), (2, 4), (3, 7), (5, 6), (6, 7), (0, 7)):
        await e.dec(w ^ (1 << a) ^ (1 << b))
    await e.check_leds()
    await e.b.expect(STATS, e.m.read(STATS), "STATS")
    await e.b.write(STATS, 1)
    e.m.write(STATS, 1)
    await e.b.expect(STATS, 0, "STATS cleared")


@cocotb.test()
async def test_random_words(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(14):
        w = encode(rng.randrange(16))
        for _ in range(rng.choice([0, 1, 1, 2, 3])):
            w ^= 1 << rng.randrange(8)
        await e.dec(w)
    await e.enc(rng.randrange(16))
    await e.b.expect(STATS, e.m.read(STATS), "STATS")
    await e.check_leds()
