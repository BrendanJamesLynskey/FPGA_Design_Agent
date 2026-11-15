"""Acceptance tests of v2_b_pdm_front against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from mic import Mic
from model import CTRL, DATA, DESIGN_ID, NEXT, STATUS, WORDS, Model


class Env_pf:
    """``pat(i)`` is the microphone bit for the i-th rising edge after RUN last went 1."""

    def __init__(self, dut) -> None:
        self.dut = dut
        self.rng = random.Random(int(cocotb.RANDOM_SEED))
        self.prbs_pf: dict[int, int] = {}
        self.pat_pf = self.random_bits_pf
        self.b = Board(dut, {"M_DATA": 0})
        self.m = Model()
        self.base_pf = 0

    def random_bits_pf(self, i: int) -> int:
        if i not in self.prbs_pf:
            self.prbs_pf[i] = self.rng.randrange(2)
        return self.prbs_pf[i]

    async def start(self) -> None:
        await self.b.start()
        self.mic = Mic(self.dut, lambda n: self.pat_pf(n - self.base_pf))

    async def wr_pf(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def go_pf(self) -> None:
        """RUN 0 -> 1. The first sample is edge 0 of the pattern."""
        self.base_pf = self.mic.n
        self.dut.M_DATA.value = self.pat_pf(0)
        await self.b.write(CTRL, 1)
        self.m.write(CTRL, 1)

    async def halt_pf(self, what: str) -> int:
        """RUN 1 -> 0, then feed_pf the model the samples the DUT took and compare_pf. Returns the number of edges seen.
        The DUT takes every rising edge's bit, except that an edge in flight at the moment RUN drops may be lost_pf."""
        await self.b.write(CTRL, 0)
        s = self.mic.n - self.base_pf
        for i in range(max(s - 1, 0)):
            self.m.sample(self.pat_pf(i))
        w = await self.b.read(WORDS)
        if w > self.m.words and s:
            self.m.sample(self.pat_pf(s - 1))
        self.m.set_run(0)
        assert w == self.m.words, f"WORDS {w}, {s} edges seen, model {self.m.words} ({what})"
        await self.compare_pf(what)
        return s

    async def compare_pf(self, what: str) -> None:
        await self.b.expect(STATUS, self.m.read(STATUS), "STATUS " + what)
        await self.b.expect(WORDS, self.m.read(WORDS), "WORDS " + what)
        await self.b.expect(DATA, self.m.read(DATA), "DATA " + what)

    async def run_samples_pf(self, n: int) -> None:
        await self.b.cycles(n * 2 * self.b.param("CLK_HALF") + 3)

    async def pop_all_pf(self, what: str) -> None:
        while self.m.q_pf:
            await self.b.expect(DATA, self.m.read(DATA), "DATA " + what)
            await self.wr_pf(NEXT, 0)
        await self.b.expect(DATA, 0, "DATA of an empty queue " + what)


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env_pf(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    for off in range(5):
        await e.b.expect(off, 0, "register at reset")
    await e.go_pf()
    await e.run_samples_pf(80)
    await e.b.reset()
    e.m = Model()
    for off in range(5):
        await e.b.expect(off, 0, "register after reset")
    assert int(dut.M_CLK.value) == 0
    assert await peek(e.b.clk, dut.LED) == 0


@cocotb.test()
async def test_clock_and_channel_select(dut):
    e = Env_pf(dut)
    await e.start()
    half_pf = e.b.param("CLK_HALF")
    await e.go_pf()
    await e.run_samples_pf(12)
    await e.b.write(CTRL, 0)
    assert len(e.mic.highs) >= 8 and len(e.mic.lows) >= 8
    assert set(e.mic.highs[1:-1]) == {half_pf} and set(e.mic.lows[1:]) == {half_pf}, \
        f"M_CLK high times {sorted(set(e.mic.highs))}, low times {sorted(set(e.mic.lows))}, want {half_pf}"
    assert not e.mic.lrsel_high_seen, "M_LRSEL must be low"
    n = e.mic.n
    for _ in range(6 * half_pf):
        assert await peek(e.b.clk, dut.M_CLK) == 0, "M_CLK must stay low while RUN = 0"
    assert e.mic.n == n
    assert await peek(e.b.clk, dut.M_LRSEL) == 0


@cocotb.test()
async def test_words_hold_the_microphone_bits(dut):
    e = Env_pf(dut)
    await e.start()
    await e.go_pf()
    await e.run_samples_pf(110)                          # three words and a bit
    s = await e.halt_pf("random bits")
    assert e.m.words >= 3 and s >= 100
    await e.pop_all_pf("random bits")


@cocotb.test()
async def test_first_bit_goes_to_the_lowest_bit(dut):
    e = Env_pf(dut)
    await e.start()
    e.pat_pf = lambda i: 1 if i % 32 in (0, 31) else (1 if i % 32 == 5 else 0)
    await e.go_pf()
    await e.run_samples_pf(70)
    await e.halt_pf("pattern 0, 5, 31")
    assert e.m.q_pf and e.m.q_pf[0] == 0x8000_0021
    await e.pop_all_pf("pattern 0, 5, 31")


@cocotb.test()
async def test_run_off_abandons_the_partial_word(dut):
    """Stop with a half_pf-built word_pf, then start again: the new run's first word_pf starts at its own first sample."""
    e = Env_pf(dut)
    await e.start()
    for attempt in range(8):
        await e.go_pf()
        await e.run_samples_pf(7 * attempt + 20)
        n = await e.halt_pf("first run")
        await e.pop_all_pf("first run")
        if 6 <= n % 32 <= 26:                         # the word_pf in progress was a real partial one
            break
    else:
        raise AssertionError("could not stop with a partial word_pf")
    e.pat_pf = lambda i: 1 if i == 0 else 0
    await e.go_pf()
    await e.run_samples_pf(40)
    await e.halt_pf("second run starts a new word_pf")
    assert e.m.words >= 2 and e.m.q_pf[0] == 1, "the second run's first word_pf starts at its own first sample"
    await e.pop_all_pf("two runs")


@cocotb.test()
async def test_queue_overflow_and_clear(dut):
    e = Env_pf(dut)
    await e.start()
    await e.go_pf()
    await e.run_samples_pf(32 * 6 + 10)                  # six words, depth is 4
    await e.halt_pf("overflow")
    assert e.m.ovr_pf == 1 and e.m.words >= 6 and len(e.m.q_pf) == 4
    await e.b.expect(STATUS, 4 | 1 << 4, "STATUS full and OVR")
    await e.wr_pf(NEXT, 0)
    await e.b.expect(STATUS, 3 | 1 << 4, "OVR stays after a pop")
    for _ in range(3):
        await e.b.expect(DATA, e.m.read(DATA), "rest of the full queue")
        await e.wr_pf(NEXT, 0)
    words = e.m.words
    await e.wr_pf(CTRL, 2)                               # CLEAR, RUN stays 0
    await e.b.expect(STATUS, 0, "CLEAR empties the queue and OVR")
    await e.b.expect(WORDS, words, "CLEAR leaves WORDS")
    await e.go_pf()
    await e.b.write(CTRL, 3)                          # CLEAR while RUN is 1: RUN and the clock carry on
    await e.b.expect(CTRL, 1, "CLEAR does not touch RUN")
    n = e.mic.n
    await e.run_samples_pf(10)
    assert e.mic.n > n, "M_CLK keeps running after CLEAR"
    await e.b.write(CTRL, 0)


@cocotb.test()
async def test_stuck_detection(dut):
    e = Env_pf(dut)
    await e.start()
    ones = lambda i: 1 if 10 <= i < 55 else (0 if i in (9, 55) else e.random_bits_pf(i))   # a run of 45 ones
    e.pat_pf = ones
    await e.go_pf()
    await e.run_samples_pf(100)
    await e.halt_pf("45 ones")
    assert e.m.hi == 1 and e.m.lo == 0
    await e.b.expect(STATUS, e.m.read(STATUS), "STUCK_HI latched")
    e.pat_pf = e.random_bits_pf
    await e.go_pf()
    await e.run_samples_pf(150)
    await e.halt_pf("random after stuck")
    assert e.m.hi == 1, "the flag stays until CLEAR"
    await e.wr_pf(CTRL, 2)
    await e.b.expect(STATUS, 0, "CLEAR drops the STUCK flags")
    # a run of 39 zeros sets nothing, a run of 40 sets STUCK_LO
    e.pat_pf = lambda i: 1 if i in (6, 46) else (0 if 7 <= i < 46 else (1 if i < 6 else e.random_bits_pf(i)))
    await e.go_pf()
    await e.run_samples_pf(100)
    await e.halt_pf("39 zeros")
    assert e.m.lo == 0
    await e.wr_pf(CTRL, 2)
    e.pat_pf = lambda i: 1 if i in (6, 47) else (0 if 7 <= i < 47 else (1 if i < 6 else e.random_bits_pf(i)))
    await e.go_pf()
    await e.run_samples_pf(100)
    await e.halt_pf("40 zeros")
    assert e.m.lo == 1 and e.m.hi == 0
    await e.b.expect(STATUS, e.m.read(STATUS), "STUCK_LO")


@cocotb.test()
async def test_stuck_run_spans_words_and_leds(dut):
    e = Env_pf(dut)
    await e.start()
    e.pat_pf = lambda i: 1 if i % 2 == 0 and i < 20 else (0 if i < 90 else e.random_bits_pf(i))    # zeros from sample 19 on
    await e.go_pf()
    await e.run_samples_pf(30)
    assert await peek(e.b.clk, dut.LED) & 1 == 1, "LED[0] shows RUN"
    await e.run_samples_pf(60)
    await e.halt_pf("zeros across a word_pf boundary")
    assert e.m.lo == 1 and e.m.leds == 2
    assert await peek(e.b.clk, dut.LED) == 2, "LED[1] shows the stuck flag, LED[0] is off with RUN"


@cocotb.test()
async def test_stuck_run_restarts_with_run(dut):
    """A stuck run that was flagged and cleared does not carry over into the next run: 25 ones are not 40."""
    e = Env_pf(dut)
    await e.start()
    e.pat_pf = lambda i: 1 if i >= 10 else e.random_bits_pf(i)
    await e.go_pf()
    await e.run_samples_pf(60)
    await e.halt_pf("a long run of ones")
    assert e.m.hi == 1
    await e.wr_pf(CTRL, 2)
    e.pat_pf = lambda i: 1 if i < 25 else i % 2
    await e.go_pf()
    await e.run_samples_pf(60)
    await e.halt_pf("25 ones after the restart")
    assert e.m.hi == 0
    await e.b.expect(STATUS, e.m.read(STATUS), "no STUCK_HI")


@cocotb.test()
async def test_register_rules(dut):
    e = Env_pf(dut)
    await e.start()
    await e.wr_pf(CTRL, 0xFFFF_FFFC)                     # bits above 1 ignored: RUN stays 0
    await e.b.expect(CTRL, 0, "CTRL")
    await e.go_pf()
    await e.b.expect(CTRL, 1, "CTRL reads RUN")
    await e.run_samples_pf(70)
    await e.halt_pf("rules")
    await e.b.write(STATUS, 0x7F)
    await e.b.write(DATA, 5)
    await e.b.write(WORDS, 9)
    await e.compare_pf("RO writes ignored, DATA read does not pop")
    await e.b.expect(DATA, e.m.read(DATA), "DATA twice")
    for off in (NEXT, 0x05, 0x40, 0x7F):
        await e.b.expect(off, 0, "write-only or unmapped reads 0")
    await e.pop_all_pf("rules")
    await e.wr_pf(NEXT, 0)                               # NEXT on empty
    await e.b.expect(STATUS, e.m.read(STATUS), "NEXT on empty")
