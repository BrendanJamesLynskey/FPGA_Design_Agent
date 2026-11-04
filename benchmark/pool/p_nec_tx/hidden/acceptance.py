"""Acceptance tests of p_nec_tx against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor
from model import ADDR, CMD, DESIGN_ID, FRAMES, REPEAT_UNITS, SEND, STATUS, Model, frame_wave, repeat_wave


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        self.u = self.b.param("UNIT_CYCLES")
        self.c = self.b.param("CARRIER_CYCLES")
        self.m = Model()

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, ir=lambda: int(self.dut.JC1.value), led=lambda: int(self.dut.LED.value))

    async def setup(self, addr: int, cmd: int) -> None:
        for off, v in ((ADDR, addr), (CMD, cmd)):
            await self.b.write(off, v)
            self.m.write(off, v)

    async def send_frame(self) -> None:
        mark = self.mon.mark()
        await self.b.write(SEND, 1)
        self.m.write(SEND, 1)
        a, c = self.m.sent
        want = frame_wave(a, c, self.u, self.c)
        await self.b.cycles(REPEAT_UNITS * self.u + 200)
        self.m.finish()
        seq = self.mon.since("ir", mark)
        t0 = next(i for i, v in enumerate(seq) if v)         # the carrier starts high
        got = seq[t0: t0 + len(want)]
        assert got == want, f"frame {a:#04x}/{c:#04x} differs at clock {next(i for i in range(len(want)) if got[i] != want[i])} of {len(want)}"
        assert not any(seq[t0 + len(want):]), "carrier after the stop mark"
        led = int(self.dut.LED.value)
        assert led >> 8 == c and led & 1 == 0, f"LED {led:04X}: LED[15:8] should show the command and LED[0] be dark when idle"
        txing = [v & 1 for v in self.mon.since("led", mark)[t0: t0 + len(want)]]
        assert sum(txing) >= len(want) - 4, "LED[0] should be lit for the whole transmission"


@cocotb.test()
async def test_identity_and_idle(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.b.cycles(100)
    assert not any(e.mon.v["ir"])
    await e.b.expect(STATUS, 0, "STATUS")


@cocotb.test()
async def test_frames_with_complements_and_carrier(dut):
    e = Env(dut)
    await e.start()
    for addr, cmd in ((0x00, 0x00), (0xFF, 0xFF), (0x04, 0x08), (0xA5, 0x5A)):
        await e.setup(addr, cmd)
        await e.send_frame()
    await e.b.expect(FRAMES, 4, "FRAMES")
    await e.b.expect(STATUS, 0, "STATUS")


@cocotb.test()
async def test_send_while_busy_is_ignored(dut):
    e = Env(dut)
    await e.start()
    await e.setup(0x12, 0x34)
    mark = e.mon.mark()
    await e.b.write(SEND, 1)
    e.m.write(SEND, 1)
    await e.b.write(SEND, 1)                      # the repeat interval is still running
    e.m.write(SEND, 1)
    await e.b.expect(STATUS, e.m.read(STATUS), "STATUS while busy")
    await e.b.cycles(REPEAT_UNITS * e.u + 200)
    e.m.finish()
    seq = e.mon.since("ir", mark)
    t0 = next(i for i, v in enumerate(seq) if v)
    want = frame_wave(0x12, 0x34, e.u, e.c)
    assert seq[t0: t0 + len(want)] == want and not any(seq[t0 + len(want):]), "the second send disturbed the line"
    await e.b.expect(STATUS, e.m.read(STATUS), "STATUS")
    await e.b.expect(FRAMES, 1, "FRAMES")


@cocotb.test()
async def test_repeat_codes_while_switch_up(dut):
    e = Env(dut)
    await e.start()
    await e.setup(0x20, 0xDF)
    dut.SW.value = 1
    await e.b.cycles(6)
    mark = e.mon.mark()
    await e.b.write(SEND, 1)
    e.m.write(SEND, 1)
    period = REPEAT_UNITS * e.u
    await e.b.cycles(2 * period + period // 2)
    dut.SW.value = 0                               # released after the second repeat has started
    await e.b.cycles(3 * period)
    e.m.finish()
    seq = e.mon.since("ir", mark)
    t0 = next(i for i, v in enumerate(seq) if v)
    frame = frame_wave(0x20, 0xDF, e.u, e.c)
    rep = repeat_wave(e.u, e.c)
    for off, want, name in ((0, frame, "frame"), (period, rep, "first repeat"), (2 * period, rep, "second repeat")):
        got = seq[t0 + off: t0 + off + len(want)]
        assert got == want, f"{name} wrong (starting {off} clocks after the frame)"
    assert not any(seq[t0 + 2 * period + len(rep):]), "something was sent after the switch went down"
    await e.b.expect(STATUS, 2 << 16, "STATUS: two repeats, idle")


@cocotb.test()
async def test_random_commands(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(3):
        await e.setup(rng.randrange(256), rng.randrange(256))
        await e.send_frame()
