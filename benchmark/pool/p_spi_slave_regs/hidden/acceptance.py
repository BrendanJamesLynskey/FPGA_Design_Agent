"""Acceptance tests of p_spi_slave_regs against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from model import BADFRAMES, DESIGN_ID, FRAMES, LASTCMD, Model, bits_of


class Env:
    def __init__(self, dut, half: int = 8) -> None:
        self.dut = dut
        self.b = Board(dut, {"JB1": 1, "JB2": 0, "JB3": 0})
        self.m = Model()
        self.half = half

    async def start(self) -> None:
        await self.b.start()

    async def frame(self, data: list[int], cut: int | None = None) -> list[int]:
        """One SPI transfer (mode 0) on JB; returns the MISO bits sampled just before each rising edge."""
        d, h = self.dut, self.half
        bits = bits_of(data)
        if cut is not None:
            bits = bits[:cut]
        d.JB1.value = 0
        await self.b.cycles(h)
        got: list[int] = []
        for b in bits:
            d.JB3.value = b
            await self.b.cycles(h - 1)
            got.append(int(d.JB4.value))
            await self.b.cycles(1)
            d.JB2.value = 1
            await self.b.cycles(h)
            d.JB2.value = 0
        await self.b.cycles(h)
        d.JB1.value = 1
        await self.b.cycles(3 * h)
        want = self.m.frame(bits)
        assert got == want, f"MISO bits {got} != model {want} for command {data[0] if data else None:#x}"
        return got

    async def check_window(self) -> None:
        for off in list(range(0, 19)):
            await self.b.expect(off, self.m.read(off), f"window {off}")
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.leds(), f"LED {led:04X} != {self.m.leds():04X}"


@cocotb.test()
async def test_identity_and_id_register(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_window()
    await e.frame([0x80, 0, 0])
    await e.frame([0x88, 0])
    await e.check_window()


@cocotb.test()
async def test_write_read_burst_and_xor(dut):
    e = Env(dut)
    await e.start()
    await e.frame([0x01, 0x11, 0x22, 0x44, 0x88])        # burst write to registers 1..4
    await e.frame([0x81] + [0] * 9)                       # burst read 1..9: the XOR register and zeros
    await e.frame([0x07, 0xF0])
    await e.frame([0x88, 0])
    await e.check_window()


@cocotb.test()
async def test_rules_for_ro_and_out_of_range(dut):
    e = Env(dut)
    await e.start()
    await e.frame([0x00, 0x99, 0x77, 0x66])               # reg 0 ignored, then regs 1 and 2 get 0x77 and 0x66
    await e.frame([0x8D] + [0] * 6)                       # 13..18
    await e.frame([0x10, 0xAA, 0xBB])
    await e.frame([0xFE] + [0] * 4)                       # 126, 127, then wraps to 0: the ID byte is read
    await e.check_window()


@cocotb.test()
async def test_partial_and_empty_frames(dut):
    e = Env(dut)
    await e.start()
    await e.frame([0x02, 0xEE], cut=12)                   # a partial data byte writes nothing
    await e.frame([0x82, 0, 0])
    await e.frame([0x03], cut=3)
    await e.frame([], cut=0)                              # CS toggled without clocks: not a frame
    await e.check_window()
    await e.b.expect(FRAMES, e.m.frames, "FRAMES")
    await e.b.expect(BADFRAMES, 2, "BADFRAMES")
    await e.b.expect(LASTCMD, e.m.last, "LASTCMD")


@cocotb.test()
async def test_shell_window_and_random_frames(dut):
    e = Env(dut, half=6)
    await e.start()
    for off, v in ((3, 0x3C), (0, 0x00), (8, 0xFF), (6, 0xC1)):
        await e.b.write(off, v)
        e.m.write(off, v)
    await e.frame([0x80] + [0] * 9)
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(6):
        n = rng.randrange(1, 6)
        if rng.random() < 0.5:
            await e.frame([rng.randrange(0x80) | 0x00] + [rng.randrange(256) for _ in range(n)])
        else:
            await e.frame([rng.randrange(0x80) | 0x80] + [0] * n)
    await e.check_window()
