"""Acceptance tests of p_seq_detect against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor, falling, rising
from model import COUNT, CTRL, DESIGN_ID, LEN, PATTERN, SAMPLES, SHIFT, Model

HOLD = 4
INV = 2


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": HOLD})
        self.m = Model()
        self.s = self.b.param("SAMPLE_CYCLES")

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, tick=lambda: (int(self.dut.LED.value) >> 1) & 1, match=lambda: int(self.dut.LED.value) & 1)

    async def next_tick(self) -> None:
        for _ in range(4 * self.s):
            await self.b.cycles(1)
            if self.mon.v["tick"][-1:] != self.mon.v["tick"][-2:-1] and len(self.mon.t) > 2:
                return
        raise AssertionError("LED[1] never toggled")

    async def feed(self, bits: list[int], inv: int = 0) -> list[bool]:
        """Release HOLD just after a sampling instant, present one bit per instant, hold again; the model takes the same bits."""
        s = self.s
        await self.next_tick()
        mark = self.mon.mark()
        await self.b.cycles(s // 4)
        self.dut.SW.value = inv
        await self.b.cycles(s // 4)
        for i, bit in enumerate(bits):
            self.dut.SW.value = bit | inv
            await self.b.cycles(s)
        await self.b.cycles(0)
        self.dut.SW.value = (bits[-1] if bits else 0) | inv | HOLD
        await self.b.cycles(s)
        seq_t = self.mon.since("tick", mark)
        seq_m = self.mon.since("match", mark)
        ticks = [i for i in range(1, len(seq_t)) if seq_t[i] != seq_t[i - 1]]
        # the instants that took a bit in are the first len(bits) instants after the release
        took = ticks[:len(bits)]
        want = self.m.feed(bits, 1 if inv else 0)
        seen = [bool(seq_m[min(i + s // 2, len(seq_m) - 1)]) for i in took]
        assert seen == want, f"LED[0] at the sampling instants {seen}, model {want}"
        return want

    async def check(self) -> None:
        for off, name in ((PATTERN, "PATTERN"), (LEN, "LEN"), (SHIFT, "SHIFT"), (COUNT, "COUNT"), (SAMPLES, "SAMPLES")):
            await self.b.expect(off, self.m.read(off), name)


@cocotb.test()
async def test_identity_and_defaults(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.b.cycles(4 * e.s)
    await e.check()                                       # held since reset: nothing counted
    assert len(rising(e.mon.v["tick"])) + len(falling(e.mon.v["tick"])) >= 3, "LED[1] must keep toggling while held"


@cocotb.test()
async def test_overlapping_matches(dut):
    e = Env(dut)
    await e.start()
    await e.feed([1, 0, 1, 1, 0, 1, 1, 0, 0])
    await e.check()
    assert e.m.count == 2


@cocotb.test()
async def test_length_pattern_invert(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(PATTERN, 0b110)
    e.m.write(PATTERN, 0b110)
    await e.b.write(LEN, 3)
    e.m.write(LEN, 3)
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.feed([1, 1, 0, 1, 1, 0, 0, 1])
    await e.check()
    await e.feed([0, 0, 1, 0, 0, 1], inv=INV)
    await e.check()


@cocotb.test()
async def test_no_match_before_len_bits_and_len_clamps(dut):
    """Leading zeros of a cleared shift register must not count as a match of an all-zero pattern."""
    e = Env(dut)
    await e.start()
    await e.b.write(PATTERN, 0)
    e.m.write(PATTERN, 0)
    await e.b.write(LEN, 5)
    e.m.write(LEN, 5)
    await e.b.write(CTRL, 1)
    e.m.write(CTRL, 1)
    await e.feed([0, 0, 0, 0, 0, 0])
    await e.check()
    assert e.m.count == 2
    for ln in (0, 12):
        await e.b.write(LEN, ln)
        e.m.write(LEN, ln)
        await e.b.write(CTRL, 1)
        e.m.write(CTRL, 1)
        await e.feed([1, 0, 1, 0, 0, 0, 0, 0, 0, 0])
        await e.check()


@cocotb.test()
async def test_random_streams(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(3):
        pat, ln = rng.randrange(256), rng.randrange(1, 9)
        await e.b.write(PATTERN, pat)
        e.m.write(PATTERN, pat)
        await e.b.write(LEN, ln)
        e.m.write(LEN, ln)
        await e.b.write(CTRL, 1)
        e.m.write(CTRL, 1)
        await e.feed([rng.randrange(2) for _ in range(14)], inv=INV if rng.random() < 0.3 else 0)
        await e.check()
