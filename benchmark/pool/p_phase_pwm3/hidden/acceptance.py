"""Acceptance tests of p_phase_pwm3 against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board
from benchmark.pool.poollib import Monitor, rising
from model import DESIGN_ID, DUTY, ON, PERIOD, STAGGER, Model


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        self.p = self.b.param("PWM_PERIOD")
        self.m = Model(self.p)

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, led=lambda: int(self.dut.LED.value) & 7)

    async def steady(self, sw: int, periods: int = 4) -> list[int]:
        """Hold sw long enough to be in use, then return `periods` periods of LED[2:0]."""
        self.dut.SW.value = sw
        await self.b.cycles(3 * self.p)
        self.m.latch(sw)
        mark = self.mon.mark()
        await self.b.cycles(periods * self.p)
        return self.mon.since("led", mark)

    def check_waveform(self, seq: list[int], sw: int) -> None:
        """Every period of seq must equal the model's waveform; the period boundary is found from channel 0."""
        w = self.m.waveform()
        if self.m.on == 0:
            assert not any(seq), "outputs not low at duty 0"
            return
        starts = rising([v & 1 for v in seq])
        assert len(starts) >= 2, "channel 0 never pulsed"
        # with STAGGER every channel's waveform is the model's, taken from channel 0's rising edge (T = 0)
        i0 = starts[0]
        n = (len(seq) - i0) // self.p
        assert n >= 2
        for p in range(n):
            got = seq[i0 + p * self.p: i0 + (p + 1) * self.p]
            assert got == w, f"period {p} of duty {sw & 0xFF}, stagger {bool(sw & 0x100)}: first mismatch at {next(i for i in range(self.p) if got[i] != w[i])}"


@cocotb.test()
async def test_identity_and_off(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    seq = await e.steady(0)
    assert not any(seq)
    await e.b.expect(PERIOD, e.p, "PERIOD")


@cocotb.test()
async def test_in_phase_duties(dut):
    e = Env(dut)
    await e.start()
    for duty in (1, 64, 128, 255):
        seq = await e.steady(duty)
        e.check_waveform(seq, duty)
        await e.b.expect(DUTY, duty, "DUTY")
        await e.b.expect(ON, e.m.on, "ON")


@cocotb.test()
async def test_staggered_channels(dut):
    e = Env(dut)
    await e.start()
    for duty in (40, 128, 200, 255):
        sw = duty | 0x100
        seq = await e.steady(sw)
        e.check_waveform(seq, sw)
    await e.b.expect(STAGGER, 1, "STAGGER")


@cocotb.test()
async def test_no_runt_pulse_when_switches_move(dut):
    e = Env(dut)
    await e.start()
    await e.steady(100)
    mark = e.mon.mark()
    await e.b.cycles(e.p // 2 + 7)
    dut.SW.value = 220                      # mid-period
    await e.b.cycles(4 * e.p)
    seq = e.mon.since("led", mark)
    ch0 = [v & 1 for v in seq]
    lens = []
    i = 0
    while i < len(ch0):
        if ch0[i]:
            j = i
            while j < len(ch0) and ch0[j]:
                j += 1
            if i > 0 and j < len(ch0):
                lens.append(j - i)
            i = j
        else:
            i += 1
    old, new = 100 * e.p // 256, 220 * e.p // 256
    assert set(lens) <= {old, new}, f"pulse lengths {lens}, only {old} or {new} are allowed"
    assert old in lens and new in lens and lens == sorted(lens, key=lambda x: x != old), f"{lens}"


@cocotb.test()
async def test_random_settings(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(5):
        sw = rng.randrange(256) | (0x100 if rng.random() < 0.6 else 0)
        seq = await e.steady(sw, 3)
        e.check_waveform(seq, sw)
