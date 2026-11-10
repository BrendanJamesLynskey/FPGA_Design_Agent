"""Acceptance tests of v2_a_seq_detect against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge
from model import COUNT, DESIGN_ID, LATENCY, LEVEL, Model

IDLE = {"JA1": 0}


class Env:
    def __init__(self, dut) -> None:
        self.dut, self.b, self.m = dut, Board(dut, IDLE), Model()

    async def start(self) -> None:
        await self.b.start()

    async def feed(self, bits) -> list[int]:
        """One bit per clock, then LATENCY idle zeros. Returns LED[0] sampled after each rising edge, and compares it
        with the model: sample n must equal the model's HIT for bit n - LATENCY."""
        clk, led = self.b.clk, self.dut.LED
        await FallingEdge(clk)
        hits = []
        got = []
        seq = list(bits) + [0] * LATENCY
        for i, bit in enumerate(seq):
            self.dut.JA1.value = bit
            await RisingEdge(clk)
            await ReadOnly()
            got.append(int(led.value))
            await FallingEdge(clk)
            hits.append(self.m.push(bit))
        for n, g in enumerate(got):
            want = hits[n - LATENCY] if n >= LATENCY else 0
            assert g & 1 == want, f"LED[0] at clock {n}: RTL {g & 1}, model {want} (stream {list(bits)})"
            assert g >> 1 == 0, f"LED[15:1] = {g >> 1:#x}, want 0"
        return got

    async def check_regs(self) -> None:
        await self.b.expect(COUNT, self.m.read(COUNT), "COUNT")
        await self.b.expect(LEVEL, self.m.read(LEVEL, int(self.dut.JA1.value)), "LEVEL")


def bits(s: str) -> list[int]:
    return [int(c) for c in s]


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_regs()
    assert int(dut.LED.value) == 0
    await e.feed(bits("0010110100"))
    await e.b.reset()
    e.m = Model()
    await e.check_regs()


@cocotb.test()
async def test_single_match_is_one_clock(dut):
    e = Env(dut)
    await e.start()
    got = await e.feed(bits("0001011000"))
    assert sum(g & 1 for g in got) == 1
    await e.check_regs()


@cocotb.test()
async def test_near_misses(dut):
    """Every four-bit window that is not 1011, and longer almost-patterns, must stay dark."""
    e = Env(dut)
    await e.start()
    for w in range(16):
        if w != 0b1011:
            await e.feed(bits("000" + format(w, "04b") + "000"))
    await e.feed(bits("1010100111010011111110000110011101010000"))   # chosen so that 1,0,1,1 never occurs
    assert e.m.count == 0
    await e.check_regs()


@cocotb.test()
async def test_overlapping_matches(dut):
    """1,0,1,1,0,1,1 holds two matches; a run of ten overlapping ones holds more."""
    e = Env(dut)
    await e.start()
    got = await e.feed(bits("0001011011000"))
    assert sum(g & 1 for g in got) == 2, "overlapping matches missed"
    got = await e.feed(bits("0" + "1011" * 1 + "011" * 4 + "0000"))
    assert sum(g & 1 for g in got) == 5
    await e.check_regs()


@cocotb.test()
async def test_random_streams(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(6):
        stream = []
        while len(stream) < 220:
            stream += bits(rng.choice(["1011", "1011", "011", "10", "1", "0", "101", "11"]))
        await e.feed(stream)
    assert e.m.count > 10
    await e.check_regs()


@cocotb.test()
async def test_count_wide_clear_and_write_ignored_bits(dut):
    """300 matches (past 8 bits), then a clear; level register follows the pin."""
    e = Env(dut)
    await e.start()
    await e.feed(bits("0" + "1011" * 300 + "0"))
    assert e.m.count == 300
    await e.check_regs()
    await e.b.write(COUNT, 0xFFFF_FFFF)            # any data clears
    e.m.clear()
    await e.check_regs()
    await e.feed(bits("00101100"))
    await e.check_regs()
    dut.JA1.value = 1
    await e.b.cycles(6)
    await e.check_regs()
    dut.JA1.value = 0
    await e.b.cycles(6)
    for off in (0x02, 0x40, 0x7F):
        await e.b.expect(off, 0, "unmapped")
