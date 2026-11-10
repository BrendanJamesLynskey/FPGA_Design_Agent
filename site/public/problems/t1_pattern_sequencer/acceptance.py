"""Acceptance tests of t1_pattern_sequencer against model.py (hidden from the agent).

A watcher logs every LED change with its clock; a playback is checked as the sequence of patterns shown and the
exact number of clocks each was shown (the first change is the start, so no absolute timing is needed)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from cocotb.triggers import ReadOnly, RisingEdge
from cocotb.utils import get_sim_time
from model import CTRL, DESIGN_ID, ENTRY0, INDEX, LENGTH, LOOPS, STATUS, Model


class Watch:
    def __init__(self, dut, clk) -> None:
        self.ev: list[tuple[int, int]] = []
        cocotb.start_soon(self.run(dut, clk))

    async def run(self, dut, clk) -> None:
        prev = None
        while True:
            await RisingEdge(clk)
            await ReadOnly()
            v = int(dut.LED.value)
            if v != prev:
                self.ev.append((int(get_sim_time("ns")) // 10, v))
            prev = v

    def take(self) -> list[tuple[int, int]]:
        ev, self.ev = self.ev, []
        return ev


def shown(ev: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """(pattern, clocks) for every change except the last (whose length is not yet known)."""
    return [(v, ev[i + 1][0] - t) for i, (t, v) in enumerate(ev[:-1])]


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, {"BTNC": 0})
        self.dut = dut
        self.n = self.b.param("DEBOUNCE_CYCLES")
        self.tick = self.b.param("TICK_CYCLES")
        self.m = Model(self.tick)
        self.w: Watch | None = None

    def now(self) -> int:
        return int(get_sim_time("ns")) // 10

    async def start(self) -> None:
        await self.b.start()
        self.w = Watch(self.dut, self.b.clk)
        await self.b.cycles(2)
        self.w.take()

    async def wr(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def program(self, entries: list[tuple[int, int]], length: int | None = None) -> None:
        for i, (pat, dur) in enumerate(entries):
            await self.wr(ENTRY0 + i, pat | dur << 16)
        if length is not None:
            await self.wr(LENGTH, length)

    async def play(self, ctrl: int, clocks: int) -> list[tuple[int, int]]:
        """Start (from stopped) and watch for ``clocks``; returns the LED changes from the start on."""
        self.w.take()
        await self.wr(CTRL, ctrl)
        await self.b.cycles(clocks)
        return self.w.take()

    async def press(self) -> int:
        self.dut.BTNC.value = 1
        t = self.now()
        await self.b.cycles(self.n + 6)
        self.dut.BTNC.value = 0
        await self.b.cycles(self.n + 6)
        return t

    async def wait_for(self, pattern: int, limit: int = 20000) -> int:
        for _ in range(limit):
            await RisingEdge(self.b.clk)
            if self.w.ev and self.w.ev[-1][1] == pattern:
                return self.w.ev[-1][0]
        raise AssertionError(f"pattern {pattern:04X} never shown")


PATS = [0x0001, 0x8000, 0x00F0, 0x0F0F, 0xAAAA, 0x5555, 0xFF00, 0x1234, 0x0420, 0xC003, 0x7E7E, 0x0101, 0x8421,
        0x3C3C, 0x6006, 0x0FF0]


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off, want in ((CTRL, 0), (LENGTH, 4), (INDEX, 0), (STATUS, 0), (LOOPS, 0), (ENTRY0, 0), (ENTRY0 + 15, 0)):
        await e.b.expect(off, want)
    assert await peek(e.b.clk, dut.LED) == 0


@cocotb.test()
async def test_loop_playback(dut):
    e = Env(dut)
    await e.start()
    durs = [3, 1, 5, 2, 4]
    await e.program([(PATS[i], d) for i, d in enumerate(durs)], length=5)
    total = sum(durs) * e.tick
    ev = await e.play(1, 2 * total + total // 2)
    want = e.m.show(len(ev) - 1)
    assert shown(ev) == want, f"shown {shown(ev)} != model {want}"
    await e.b.expect(STATUS, 1, "STATUS running")
    await e.wr(CTRL, 0)                         # stop: LEDs dark
    await e.b.expect(STATUS, 0, "STATUS stopped")
    assert await peek(e.b.clk, dut.LED) == 0
    loops = await e.b.read(LOOPS)
    assert loops >= 2, f"LOOPS {loops} after more than two passes"


@cocotb.test()
async def test_one_shot_holds_last(dut):
    e = Env(dut)
    await e.start()
    await e.program([(PATS[i], 2 + i) for i in range(6)], length=3)
    ev = await e.play(0b11, 20 * e.tick + 2000)
    assert [v for _, v in ev] == PATS[:3], f"one-shot showed {[hex(v) for _, v in ev]}"
    assert shown(ev) == e.m.show(2)
    await e.b.expect(STATUS, 0b100, "STATUS DONE")
    await e.b.expect(INDEX, 2, "INDEX of the last entry")
    await e.b.expect(LOOPS, 1, "LOOPS")
    await e.b.expect(CTRL, 0b10, "CTRL after one-shot")
    assert await peek(e.b.clk, dut.LED) == PATS[2], "LEDs must hold the last pattern"
    ev = await e.play(0b11, 20 * e.tick)        # starts again from entry 0
    assert ev and ev[0][1] == PATS[0]
    await e.wr(CTRL, 0)                         # stop clears DONE and darkens
    await e.b.expect(STATUS, 0, "STATUS")
    assert await peek(e.b.clk, dut.LED) == 0


@cocotb.test()
async def test_pause_button(dut):
    e = Env(dut)
    await e.start()
    await e.program([(PATS[i], 100) for i in range(3)], length=3)
    e.w.take()
    await e.wr(CTRL, 1)
    t_on = await e.wait_for(PATS[0])
    await e.b.cycles(3 * e.tick)
    r1 = await e.press()                        # pause
    await e.b.expect(STATUS, 0b011, "STATUS paused")
    assert await peek(e.b.clk, dut.LED) == PATS[0]
    await e.b.cycles(2000)
    r2 = await e.press()                        # resume
    t_next = await e.wait_for(PATS[1])
    assert t_next - t_on == 100 * e.tick + (r2 - r1), \
        f"entry 0 lasted {t_next - t_on} clocks, want {100 * e.tick} + paused {r2 - r1}"
    await e.b.expect(STATUS, 0b001, "STATUS resumed")
    await e.wr(CTRL, 0)
    await e.press()                             # stopped: a press does nothing
    await e.b.expect(STATUS, 0, "STATUS")


@cocotb.test()
async def test_zero_duration_is_256(dut):
    e = Env(dut)
    await e.start()
    await e.program([(PATS[0], 0), (PATS[1], 3)], length=2)
    ev = await e.play(1, 256 * e.tick + 3 * e.tick + 200)
    assert shown(ev)[:2] == e.m.show(2), f"shown {shown(ev)[:2]}, want {e.m.show(2)}"


@cocotb.test()
async def test_length_rules(dut):
    e = Env(dut)
    await e.start()
    await e.program([(PATS[i], 4) for i in range(4)] + [(PATS[4], 120)], length=5)
    await e.wr(LENGTH, 0)                       # ignored
    await e.wr(LENGTH, 17)                      # ignored
    await e.b.expect(LENGTH, 5, "LENGTH")
    e.w.take()
    await e.wr(CTRL, 1)
    await e.wait_for(PATS[4])                   # entry 4 is long: change LENGTH while it plays
    await e.wr(LENGTH, 2)
    await e.b.cycles(120 * e.tick + 20 * e.tick)
    ev = e.w.take()
    vals = [v for _, v in ev]
    assert vals[:5] == PATS[:5] and vals[5:9] == [PATS[0], PATS[1], PATS[0], PATS[1]], \
        f"after LENGTH = 2 the show must wrap after entry 1: {[hex(v) for v in vals]}"


@cocotb.test()
async def test_live_pattern_edit(dut):
    e = Env(dut)
    await e.start()
    await e.program([(PATS[0], 3), (PATS[1], 150), (PATS[2], 3)], length=3)
    e.w.take()
    await e.wr(CTRL, 1)
    t1 = await e.wait_for(PATS[1])
    await e.wr(ENTRY0 + 1, 0x0BAD | 150 << 16)  # shows at once; the entry's timing is unchanged
    assert await peek(e.b.clk, dut.LED) == 0x0BAD
    t2 = await e.wait_for(PATS[2])
    assert t2 - t1 == 150 * e.tick, f"entry 1 lasted {t2 - t1} clocks after a live edit"
    await e.b.expect(ENTRY0 + 1, 0x0BAD | 150 << 16, "ENTRY1")


@cocotb.test()
async def test_start_is_from_entry_zero(dut):
    e = Env(dut)
    await e.start()
    await e.program([(PATS[i], 200) for i in range(4)], length=4)
    e.w.take()
    await e.wr(CTRL, 1)
    await e.wait_for(PATS[2])
    await e.wr(CTRL, 0b11)                      # RUN = 1 while running: no restart, now one-shot
    await e.b.expect(INDEX, 2, "INDEX")
    await e.wr(CTRL, 0)
    assert await peek(e.b.clk, dut.LED) == 0
    ev = await e.play(1, 200)                   # restart: entry 0 first
    assert ev[0][1] == PATS[0]


@cocotb.test()
async def test_debounce_rejects_bounce(dut):
    e = Env(dut)
    await e.start()
    await e.program([(PATS[i], 20) for i in range(2)], length=2)
    await e.wr(CTRL, 1)
    for width in (1, 3, e.n // 2, e.n - 3):
        dut.BTNC.value = 1
        await e.b.cycles(width)
        dut.BTNC.value = 0
        await e.b.cycles(e.n + 4)
    await e.b.expect(STATUS, 1, "glitches must not pause")


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.start()
    await e.wr(ENTRY0 + 7, 0xFFFF_FFFF)
    await e.b.expect(ENTRY0 + 7, 0x00FF_FFFF, "ENTRY7 keeps [23:0]")
    await e.wr(CTRL, 0xFFFF_FFFC)               # RUN 0, ONESHOT 0
    await e.b.expect(CTRL, 0, "CTRL")
    for off in (INDEX, STATUS, LOOPS):
        await e.b.write(off, 3)
    await e.b.expect(INDEX, 0)
    await e.b.expect(STATUS, 0)
    await e.b.expect(LOOPS, 0)
    for off in (0x05, 0x0F, 0x20, 0x7F):
        await e.b.expect(off, 0, "unmapped")


@cocotb.test()
async def test_random_program(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    n = rng.randrange(2, 17)
    pats = rng.sample(range(1, 65536), n)
    entries = [(p, rng.randrange(1, 12)) for p in pats]
    await e.program(entries, length=n)
    total = sum(d for _, d in entries) * e.tick
    ev = await e.play(1, total + total // 2 + 200)
    want = e.m.show(len(ev) - 1)
    assert shown(ev) == want, f"shown {shown(ev)} != model {want}"
