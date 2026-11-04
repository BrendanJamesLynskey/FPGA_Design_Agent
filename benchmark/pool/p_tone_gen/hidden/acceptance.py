"""Acceptance tests of p_tone_gen against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from benchmark.pool.poollib import Monitor, runs
from model import DESIGN_ID, HALF, NOTE, TOGGLES, Model

ON = 0x8000


class Env:
    def __init__(self, dut) -> None:
        self.dut = dut
        self.b = Board(dut, {"SW": 0})
        self.m = Model(self.b.param("NOTE_BASE"))

    async def start(self) -> None:
        await self.b.start()
        self.mon = Monitor(self.b.clk, pwm=lambda: int(self.dut.AUD_PWM.value), sd=lambda: int(self.dut.AUD_SD.value))

    async def play(self, sw: int, halves: int = 8) -> list[int]:
        """Hold sw (sound on), return the lengths of the complete half-waves seen in about `halves` half-waves."""
        self.dut.SW.value = sw
        self.m.sw = sw
        await self.b.cycles(3 * self.m.half + 10)
        mark = self.mon.mark()
        await self.b.cycles(halves * self.m.half + 5)
        return [n for _, _, n in runs(self.mon.since("pwm", mark))[1:-1]]


@cocotb.test()
async def test_identity_and_silence(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.b.cycles(400)
    assert not any(e.mon.v["pwm"]) and not any(e.mon.v["sd"]), "sound while off"
    await e.b.expect(TOGGLES, 0, "TOGGLES")


@cocotb.test()
async def test_every_note_and_octave(dut):
    e = Env(dut)
    await e.start()
    for octave in (0, 1):
        for note in range(8):
            sw = ON | octave << 3 | note
            lens = await e.play(sw)
            assert lens and set(lens) == {e.m.half}, f"note {note} octave {octave}: half-waves {lens}, want {e.m.half}"
            assert int(dut.AUD_SD.value) == 1
    await e.b.expect(NOTE, e.m.read(NOTE), "NOTE")
    await e.b.expect(HALF, e.m.half, "HALF")
    led = await peek(e.b.clk, dut.LED)
    assert led == e.m.leds(), f"LED {led:04X} != {e.m.leds():04X}"


@cocotb.test()
async def test_note_change_never_shortens_a_half_wave(dut):
    e = Env(dut)
    await e.start()
    await e.play(ON | 0)                              # lowest note, long half-waves
    old = e.m.half
    e.m.sw = ON | 7
    mark = e.mon.mark()
    await e.b.cycles(old // 3)
    dut.SW.value = ON | 7
    await e.b.cycles(6 * old)
    lens = [n for _, _, n in runs(e.mon.since("pwm", mark))[1:-1]]
    new = e.m.half
    assert min(lens) >= new and lens[0] in (old, new) and set(lens) <= {old, new}, f"half-waves {lens} (old {old}, new {new})"
    assert lens[-1] == new


@cocotb.test()
async def test_off_silences_and_toggle_count(dut):
    e = Env(dut)
    await e.start()
    await e.b.write(TOGGLES, 0)
    await e.play(ON | 3, 12)
    dut.SW.value = 0
    await e.b.cycles(40)
    assert int(dut.AUD_SD.value) == 0 and int(dut.AUD_PWM.value) == 0
    t = await e.b.read(TOGGLES)
    edges = sum(1 for a, b in zip(e.mon.v["pwm"], e.mon.v["pwm"][1:]) if a != b)
    assert abs(t - (edges - 1)) <= 2 and t > 10, f"TOGGLES {t}, edges seen {edges}"
    await e.b.write(TOGGLES, 1)
    await e.b.expect(TOGGLES, 0, "TOGGLES cleared")


@cocotb.test()
async def test_random_notes(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for _ in range(6):
        sw = ON | rng.randrange(16)
        lens = await e.play(sw, 6)
        assert lens and set(lens) == {e.m.half}, f"sw {sw:04X}: {lens} want {e.m.half}"
