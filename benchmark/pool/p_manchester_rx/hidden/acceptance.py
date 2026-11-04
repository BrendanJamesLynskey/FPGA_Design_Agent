"""Acceptance tests of p_manchester_rx against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import CTRL, DATA, DESIGN_ID, E_CODING, E_PARITY, E_PREAMBLE, GOOD, Model, frame


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"JB1": 0})
        self.bc = self.b.param("BIT_CYCLES")
        self.m = Model(self.bc)

    async def start(self) -> None:
        await self.b.start()
        await self.b.cycles(3 * self.bc)                # quiet low line so the receiver is armed

    async def drive(self, bits: list[int], flat: int | None = None) -> None:
        """Put a frame on JB1: 1 = low then high, 0 = high then low; bit `flat` (a 1 bit, not the first) has no transition and stays high."""
        h = self.bc // 2
        for j, b in enumerate(bits):
            first, second = (0, 1) if b else (1, 0)
            if j == flat:
                first = second
            self.dut.JB1.value = first
            await self.b.cycles(h)
            self.dut.JB1.value = second
            await self.b.cycles(h)
        self.dut.JB1.value = 0
        await self.b.cycles(4 * self.bc)                 # quiet low line: re-arm

    async def send(self, bits: list[int], flat: int | None = None) -> None:
        self.m.receive(bits, flat)
        await self.drive(bits, flat)

    async def check(self) -> None:
        for off, name in ((DATA, "DATA"), (GOOD, "GOOD"), (E_CODING, "E_CODING"), (E_PREAMBLE, "E_PREAMBLE"), (E_PARITY, "E_PARITY")):
            await self.b.expect(off, self.m.read(off), name)
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != model {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_idle(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check()


@cocotb.test()
async def test_good_frames(dut):
    e = Env(dut)
    await e.start()
    for byte in (0xA5, 0x00, 0xFF, 0x01, 0x80, 0x3C):
        await e.send(frame(byte))
        await e.check()
    assert e.m.good == 6


@cocotb.test()
async def test_error_classes(dut):
    e = Env(dut)
    await e.start()
    await e.send(frame(0x42))
    await e.send(frame(0x42, parity_flip=True))
    bad = frame(0x42)
    bad[3] = 0
    await e.send(bad)                                   # lead-in 1110 0 ...: wrong lead-in
    await e.send(frame(0x42), flat=6)                   # a data bit (a 1) without its transition
    await e.send(frame(0x42), flat=1)                   # a lead-in bit without its transition
    await e.check()
    assert e.m.e == {"coding": 2, "preamble": 1, "parity": 1}
    await e.send(frame(0x99))                           # the receiver recovers after all of that
    await e.check()


@cocotb.test()
async def test_clear_counts(dut):
    e = Env(dut)
    await e.start()
    await e.send(frame(0x11))
    await e.send(frame(0x11, True))
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.check()
    await e.send(frame(0x22))
    await e.check()


@cocotb.test()
async def test_random_traffic(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(8):
        byte = rng.randrange(256)
        r = rng.random()
        if r < 0.6:
            await e.send(frame(byte))
        elif r < 0.8:
            await e.send(frame(byte, True))
        else:
            ones = [j for j, b in enumerate(frame(byte)) if b == 1 and j > 0]
            await e.send(frame(byte), flat=rng.choice(ones))
    await e.check()
