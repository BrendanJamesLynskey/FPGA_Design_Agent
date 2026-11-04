"""Acceptance tests of p_manchester_tx against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor
from model import DATA, DESIGN_ID, SENT, STATUS, Model, waveform


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {})
        self.m = Model()
        self.bit = self.b.param("BIT_CYCLES")

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, line=lambda: int(self.dut.JB1.value), led=lambda: int(self.dut.LED.value))

    async def send(self, byte: int) -> None:
        mark = self.mon.mark()
        await self.b.write(DATA, byte)
        self.m.write(DATA, byte)
        await self.b.cycles(14 * self.bit + 300)
        self.m.finish()
        seq = self.mon.since("line", mark)
        first = next((i for i, v in enumerate(seq) if v), None)
        assert first is not None, "no frame on JB1"
        t0 = first - self.bit // 2                  # the first lead-in bit is low for its first half, hidden in the idle level
        want = waveform(byte, self.bit)
        got = seq[t0: t0 + len(want)]
        assert got == want, f"byte {byte:#04x}: line differs from the Manchester frame at clock {next(i for i in range(len(want)) if got[i] != want[i])}"
        assert not any(seq[t0 + len(want):]), "line not low after the frame"
        assert not any(seq[:t0]), "line not low before the frame"


@cocotb.test()
async def test_identity_and_idle(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.b.cycles(50)
    assert not any(e.mon.v["line"])
    for off in (DATA, STATUS, SENT):
        await e.b.expect(off, 0, "register")


@cocotb.test()
async def test_frames_exact(dut):
    e = Env(dut)
    await e.start()
    for byte in (0x00, 0xFF, 0xA5, 0x01, 0x80):
        await e.send(byte)
        await e.b.expect(SENT, e.m.read(SENT), "SENT")


@cocotb.test()
async def test_second_byte_while_busy_is_dropped(dut):
    e = Env(dut)
    await e.start()
    mark = e.mon.mark()
    await e.b.write(DATA, 0x3C)
    e.m.write(DATA, 0x3C)
    await e.b.write(DATA, 0xC3)                    # still sending the first frame
    e.m.write(DATA, 0xC3)
    await e.b.expect(STATUS, e.m.read(STATUS), "STATUS while busy")
    await e.b.cycles(14 * e.bit + 300)
    e.m.finish()
    seq = e.mon.since("line", mark)
    first = next(i for i, v in enumerate(seq) if v) - e.bit // 2
    assert seq[first: first + 14 * e.bit] == waveform(0x3C, e.bit), "the first frame was disturbed"
    assert not any(seq[first + 14 * e.bit:]), "a second frame went out"
    await e.b.expect(STATUS, e.m.read(STATUS), "STATUS")
    await e.b.expect(SENT, 1, "SENT")
    await e.b.expect(DATA, 0x3C, "DATA keeps the accepted byte")


@cocotb.test()
async def test_leds_follow_line_and_busy(dut):
    e = Env(dut)
    await e.start()
    mark = e.mon.mark()
    await e.send(0x96)
    line, led = e.mon.since("line", mark), e.mon.since("led", mark)
    assert all((l & 1) == x for l, x in zip(led, line)), "LED[0] != line"
    busy = [(l >> 1) & 1 for l in led]
    assert sum(busy) in range(14 * e.bit - 4, 14 * e.bit + 12), f"BUSY lit for {sum(busy)} clocks"


@cocotb.test()
async def test_random_bytes(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(4):
        await e.send(rng.randrange(256))
    await e.b.expect(SENT, 4, "SENT")
