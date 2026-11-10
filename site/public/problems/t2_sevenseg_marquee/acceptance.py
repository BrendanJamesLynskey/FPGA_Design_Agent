"""Acceptance tests of t2_sevenseg_marquee against model.py (hidden from the agent)."""

from __future__ import annotations

import random

import cocotb
from cocotb.utils import get_sim_time
from benchmark.lib.bench import Board
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge
from model import CTRL, DESIGN_ID, DIM, DIR, LENGTH, MSG0, POS, SCROLL, Model

PINS = ("CA", "CB", "CC", "CD", "CE", "CF", "CG", "DP")
ODD = [0x49, 0x80, 0x36, 0x01, 0x7F, 0x63, 0x5C, 0xC9, 0x14, 0x22, 0x08, 0x41, 0x2A, 0x55, 0x9C, 0xF0]


class Env:
    def __init__(self, dut) -> None:
        self.b = Board(dut)
        self.dut, self.m = dut, Model()
        self.rb = self.b.param("REFRESH_BITS")
        self.slot = 1 << self.rb
        self.scroll = self.b.param("SCROLL_CYCLES")

    async def start(self) -> None:
        await self.b.start()

    async def wr(self, off: int, v: int) -> None:
        await self.b.write(off, v)
        self.m.write(off, v)

    async def regs(self) -> None:
        for off in (CTRL, LENGTH, POS, DIM):
            await self.b.expect(off, self.m.read(off), f"window 0x{off:02X}")

    async def scan(self) -> tuple[dict[int, set[int]], list[tuple[int | None, int]]]:
        """Watch 9 slots: per digit, the set of segment patterns while lit, and the runs (digit or None, clocks)."""
        pats: dict[int, set[int]] = {}
        runs: list[tuple[int | None, int]] = []
        cur, n = -1, 0
        for _ in range(9 * self.slot):
            await RisingEdge(self.b.clk)
            await ReadOnly()
            an = int(self.dut.AN.value)
            low = [k for k in range(8) if not (an >> k) & 1]
            assert len(low) <= 1, f"more than one digit lit: AN=0b{an:08b}"
            k = low[0] if low else None
            if k is not None:
                pats.setdefault(k, set()).add(sum(int(getattr(self.dut, p).value) << i for i, p in enumerate(PINS)))
            if k != cur:
                runs.append((cur, n))
                cur, n = k, 0
            n += 1
        await FallingEdge(self.b.clk)
        return pats, runs[2:]                    # drop the start-up entry and the first (partial) run

    async def check_display(self, check_dim: bool = True) -> None:
        pats, runs = await self.scan()
        want = self.m.display()
        got = {k: next(iter(v)) if len(v) == 1 else sorted(v) for k, v in pats.items()}
        assert got == want, f"digits (active-low DP..A) RTL {got} != model {want}"
        if check_dim:
            lit = self.m.lit_clocks(self.rb)
            lit_runs = [n for k, n in runs if k is not None]
            assert len(lit_runs) >= 6 and all(n == lit for n in lit_runs), \
                f"lit runs {lit_runs} clocks, model {lit} (DIM {self.m.dim})"
            order = [k for k, _ in runs if k is not None]
            assert all((b - a) % 8 == 1 for a, b in zip(order, order[1:])), f"scan order {order}"


@cocotb.test(timeout_time=1613150, timeout_unit="ns")
async def test_identity_and_reset(dut):
    e = Env(dut)
    await e.start()
    assert await e.b.shell_id() == DESIGN_ID
    await e.regs()
    for off in list(range(MSG0, MSG0 + 16)) + [0x04, 0x0F, 0x20, 0x7F]:
        await e.b.expect(off, 0, f"window 0x{off:02X}")
    await e.check_display()


@cocotb.test(timeout_time=1393260, timeout_unit="ns")
async def test_raw_segment_bytes(dut):
    """Trap: the textbook drives the digits through a hex-glyph decoder; here each byte is the raw segment pattern
    (0x49 lights a, d and g, a symbol no hex digit uses; 0x80 is the decimal point alone)."""
    e = Env(dut)
    await e.start()
    for i, v in enumerate(ODD[:8]):
        await e.wr(MSG0 + i, v)
    await e.check_display()
    for i in range(8):
        await e.b.expect(MSG0 + i, ODD[i], f"MSG{i}")


@cocotb.test(timeout_time=2136090, timeout_unit="ns")
async def test_window_wraps(dut):
    e = Env(dut)
    await e.start()
    for i, v in enumerate(ODD):
        await e.wr(MSG0 + i, v)
    for length, pos in ((16, 12), (5, 3), (1, 0), (8, 7), (3, 2)):
        await e.wr(LENGTH, length)
        await e.wr(POS, pos)
        await e.regs()
        await e.check_display()


@cocotb.test(timeout_time=2585780, timeout_unit="ns")
async def test_length_and_pos_rules(dut):
    e = Env(dut)
    await e.start()
    for off, v in ((LENGTH, 0), (LENGTH, 17), (LENGTH, 0x101), (LENGTH, 12), (POS, 12), (POS, 11), (POS, 0x10),
                   (LENGTH, 11), (LENGTH, 4), (POS, 3), (LENGTH, 3), (CTRL, 0xFFFF_FFFC), (DIM, 0x0B)):
        await e.wr(off, v)
        await e.regs()


@cocotb.test(timeout_time=1331410, timeout_unit="ns")
async def test_dimming(dut):
    e = Env(dut)
    await e.start()
    for i, v in enumerate(ODD[8:]):
        await e.wr(MSG0 + i, v)
    for d in (0, 3, 6, 7, 1):
        await e.wr(DIM, d)
        await e.check_display()


@cocotb.test(timeout_time=2839520, timeout_unit="ns")
async def test_scroll_steps(dut):
    e = Env(dut)
    await e.start()
    for i, v in enumerate(ODD):
        await e.wr(MSG0 + i, v)
    await e.wr(LENGTH, 10)
    await e.wr(POS, 8)
    await e.wr(CTRL, SCROLL)                      # the counter restarts at this write (~560 clocks before it returns)
    # POS read (its win_rd comes ~640 clocks into the access) at 2.5 steps after the write: between steps 2 and 3
    await e.b.cycles(int(2.5 * e.scroll) - 560 - 640)
    e.m.step(2)
    await e.b.expect(POS, e.m.pos, "POS after 2.5 scroll periods")   # 8 -> 9 -> 0 (wraps at LENGTH 10)
    # exact step period: watch POS change on the display (digit 7 shows MSG[POS])
    times = []
    last = None
    while len(times) < 3:
        await RisingEdge(e.b.clk)
        await ReadOnly()
        if not int(dut.AN.value) >> 7 & 1:
            v = sum(int(getattr(dut, p).value) << i for i, p in enumerate(PINS))
            if last is not None and v != last:
                times.append(int(get_sim_time("ns")) // 10)
            last = v
    await FallingEdge(e.b.clk)
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert all(abs(g - e.scroll) <= 8 * e.slot for g in gaps), f"scroll steps {gaps} clocks apart, model {e.scroll}"
    await e.wr(CTRL, SCROLL | DIR)                # now right: POS decreases; the counter restarts
    pos_now = await e.b.read(POS)                 # ~1200 clocks after the write took effect
    e.m.pos = pos_now
    await e.b.cycles(int(1.5 * e.scroll) - 1760 - 640)
    e.m.step(1)
    await e.b.expect(POS, e.m.pos, "POS 1.5 periods after DIR = 1")
    await e.wr(CTRL, 0)
    await e.b.cycles(2 * e.scroll)
    await e.regs()                                 # stopped
    await e.check_display()
    # a POS write restarts the scroll counter: write it 0.6 period after enabling, read it 0.8 period later
    await e.wr(CTRL, SCROLL)
    await e.b.cycles(int(0.6 * e.scroll) - 1200)
    await e.wr(POS, 5)
    await e.b.cycles(int(0.8 * e.scroll) - 1200)
    await e.b.expect(POS, 5, "POS 0.8 period after a POS write (the counter restarts)")
    await e.wr(CTRL, 0)


@cocotb.test(timeout_time=2181770, timeout_unit="ns")
async def test_random_windows(dut):
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    for i in range(16):
        await e.wr(MSG0 + i, rng.randrange(256))
    for _ in range(4):
        await e.wr(LENGTH, rng.randrange(1, 17))
        await e.wr(POS, rng.randrange(16))
        await e.wr(DIM, rng.randrange(8))
        await e.wr(MSG0 + rng.randrange(16), rng.randrange(256))
        await e.regs()
        await e.check_display()
