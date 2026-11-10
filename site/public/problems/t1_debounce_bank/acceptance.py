"""Acceptance tests of t1_debounce_bank against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from benchmark.lib.bench import Board, peek
from cocotb.triggers import ReadOnly, RisingEdge
from cocotb.utils import get_sim_time
from model import COUNT0, DESIGN_ID, EDGES, FALL_EN, LEVEL, RISE_EN, Model

NAMES = {LEVEL: "LEVEL", EDGES: "EDGES", RISE_EN: "RISE_EN", FALL_EN: "FALL_EN", 4: "COUNT0", 5: "COUNT1",
         6: "COUNT2", 7: "COUNT3"}


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut, {"SW": 0})
        self.dut, self.m = dut, Model()
        self.n = self.b.param("DEBOUNCE_CYCLES")
        self.sw = 0

    async def start(self) -> None:
        await self.b.start()

    async def set_sw(self, v: int, settle: bool = True) -> None:
        self.sw = v & 0xFFFF
        self.dut.SW.value = self.sw
        if settle:
            await self.b.cycles(self.n + 8)
            self.m.settle(self.sw)

    async def wr(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def check_regs(self) -> None:
        for off in range(8):
            await self.b.expect(off, self.m.read(off), NAMES[off])

    async def check_leds(self) -> None:
        led = await peek(self.b.clk, self.dut.LED)
        assert led == self.m.level, f"LED {led:04X} != model {self.m.level:04X}"


@cocotb.test()
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.check_regs()
    await e.check_leds()


@cocotb.test()
async def test_glitch_on_slow_tick(dut):
    """Trap: the textbook debouncer samples each switch on a slow tick, so a short glitch that happens to cover a
    sampling instant changes the level. Glitches of 3 clocks are swept across every phase of a DEBOUNCE_CYCLES
    period (and longer ones up to DEBOUNCE_CYCLES - 1): none may change any level."""
    e = Env(dut)
    await e.start()
    await e.set_sw(0x0F0F)
    await e.check_regs()
    base = e.sw
    for width, step in ((3, 3), (e.n - 1, 1), (e.n // 2, 5)):
        for _ in range(e.n // step + 2):
            dut.SW.value = base ^ 0xFFFF
            await e.b.cycles(width)
            dut.SW.value = base
            await e.b.cycles(e.n + step)
    await e.b.cycles(e.n + 8)
    await e.check_regs()                         # no level change, no count, no edge beyond the first settle
    await e.check_leds()


@cocotb.test()
async def test_levels_follow_switches(dut):
    e = Env(dut)
    await e.start()
    for v in (0x0001, 0x8000, 0xFFFF, 0x0000, 0xA5C3, 0x5A3C):
        await e.set_sw(v)
        await e.check_leds()
        await e.b.expect(LEVEL, e.m.read(LEVEL), "LEVEL")
    await e.check_regs()


@cocotb.test()
async def test_independent_timing(dut):
    """Each switch has its own debounce: a change on one never restarts or delays another."""
    e = Env(dut)
    await e.start()
    seen: dict[int, int] = {}

    async def watch():
        prev = 0
        while True:
            await RisingEdge(e.b.clk)
            await ReadOnly()
            v = int(dut.LED.value)
            for k in range(16):
                if (v ^ prev) >> k & 1 and k not in seen:
                    seen[k] = int(get_sim_time("ns")) // 10
            prev = v

    cocotb.start_soon(watch())
    t0 = int(get_sim_time("ns")) // 10
    dut.SW.value = 1 << 3                       # switch 3 up at t0
    await e.b.cycles(e.n // 2)
    dut.SW.value = 1 << 3 | 1 << 9              # switch 9 up half a debounce later
    for _ in range(3):                          # switch 12 chatters meanwhile
        await e.b.cycles(e.n // 6)
        dut.SW.value = int(dut.SW.value) | 1 << 12
        await e.b.cycles(2)
        dut.SW.value = int(dut.SW.value) & ~(1 << 12)
    await e.b.cycles(2 * e.n)
    assert set(seen) == {3, 9}, f"LEDs that changed: {sorted(seen)}"
    assert seen[9] - seen[3] == e.n // 2, f"switch 9 settled {seen[9] - seen[3]} clocks after 3, want {e.n // 2}"
    # v1.2: n + 1 .. n + 8 clocks (a two- to four-flop synchroniser plus one output register all pass)
    assert seen[3] - t0 - e.n in range(1, 9), f"switch 3 took {seen[3] - t0} clocks to settle"
    e.sw = 1 << 3 | 1 << 9
    e.m.settle(e.sw)
    await e.check_regs()


@cocotb.test()
async def test_counts_and_clear(dut):
    e = Env(dut)
    await e.start()
    for k, n in ((0, 3), (5, 2), (7, 5), (14, 1), (15, 4)):
        for _ in range(n):
            await e.set_sw(e.sw ^ 1 << k)
    await e.check_regs()
    await e.wr(5, 0x1234)                       # clears counts 4..7 only
    await e.check_regs()
    for _ in range(258):                        # count 0 wraps at 256
        await e.set_sw(e.sw ^ 1)
    await e.check_regs()


@cocotb.test()
async def test_edge_selection_and_w1c(dut):
    e = Env(dut)
    await e.start()
    await e.wr(RISE_EN, 0x00FF)
    await e.wr(FALL_EN, 0x0F0F)
    await e.set_sw(0xFFFF)                      # rises: EDGES 0x00FF
    await e.check_regs()
    await e.wr(EDGES, 0x000F)                   # W1C: clear four
    await e.check_regs()
    await e.wr(EDGES, 0)                        # zeros clear nothing
    await e.check_regs()
    await e.set_sw(0x0000)                      # falls: adds 0x0F0F
    await e.check_regs()
    await e.wr(EDGES, 0xFFFF)
    await e.wr(RISE_EN, 0)
    await e.wr(FALL_EN, 0)
    await e.set_sw(0xFFFF)                      # nothing selected: no flags, counts still move
    await e.set_sw(0x0000)
    await e.check_regs()


@cocotb.test()
async def test_bounce_then_steady(dut):
    e = Env(dut)
    await e.start()
    for w in (2, 7, 4, 11, 3):
        dut.SW.value = 0x0101
        await e.b.cycles(w)
        dut.SW.value = 0
        await e.b.cycles(w)
    await e.set_sw(0x0101)                      # one rise each, however much chatter before
    await e.check_regs()


@cocotb.test()
async def test_register_rules(dut):
    e = Env(dut)
    await e.start()
    await e.set_sw(0x00F0)
    await e.b.write(LEVEL, 0xFFFF)              # read-only
    await e.wr(RISE_EN, 0xABCD_1234)            # [15:0] only
    await e.wr(FALL_EN, 0x1_0000)
    await e.check_regs()
    for off in (0x08, 0x40, 0x7F):
        await e.b.expect(off, 0, "unmapped")


@cocotb.test()
async def test_random_activity(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    await e.wr(RISE_EN, rng.getrandbits(16))
    await e.wr(FALL_EN, rng.getrandbits(16))
    for _ in range(25):
        r = rng.random()
        if r < 0.15:
            mask = rng.getrandbits(16)
            dut.SW.value = e.sw ^ mask          # a glitch: shorter than the debounce time
            await e.b.cycles(rng.randrange(1, e.n))
            dut.SW.value = e.sw
            await e.b.cycles(e.n + 4)
        elif r < 0.25:
            await e.wr(rng.choice((EDGES, 4, 5, 6, 7)), rng.getrandbits(32))
        else:
            await e.set_sw(e.sw ^ rng.getrandbits(16))
    await e.check_regs()
    await e.check_leds()
