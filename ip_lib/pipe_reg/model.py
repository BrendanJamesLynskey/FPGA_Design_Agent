"""Cycle-accurate golden model for ip_lib/pipe_reg, written from the behaviour each mode is specified to have, not from the RTL.

A slice is a small FIFO with a stated capacity and a stated rule for when it says "ready":
    COMB   capacity 1; ready = empty or the output is taken in this clock (a combinational path through the slice)
    HALF   capacity 1; ready is a register: high in a clock if the slice was empty after the previous edge
    SKID   capacity 2; ready is a register: high in a clock if the slice held fewer than 2 beats after the previous edge
    FULL   capacity 2; same rule as SKID (the two are specified to behave cycle for cycle alike)
All of them show a beat at the output one clock after it was accepted (valid = not empty), and the register that
holds ready is low in reset and for the first clock after reset. FWD is a shift register of N stages with one shared
enable (stages advance when the last stage is empty or taken).
`step` takes the three input signals of one clock (s_valid, s_data, m_ready) and returns the signals visible in that
clock *before* the edge (s_ready, m_valid, m_data), then advances the state to after the edge.
Also: `latency`, `throughput`, `capacity`, the declared figures the tests measure.
"""
from __future__ import annotations

from fractions import Fraction

FWD, SKID, FULL, HALF, COMB = 0, 1, 2, 3, 4
NAMES = {FWD: "FWD", SKID: "SKID", FULL: "FULL", HALF: "HALF", COMB: "COMB"}


class Slice:
    def __init__(self, mode: int):
        self.mode = mode
        self.cap = 2 if mode in (SKID, FULL) else 1
        self.q: list[int] = []
        self.rdy = False                        # the ready register (not used by COMB)

    def reset(self):
        self.q, self.rdy = [], False

    def m_valid(self) -> bool:
        return bool(self.q)

    def m_data(self):
        return self.q[0] if self.q else None

    def s_ready(self, m_ready: bool) -> bool:
        if self.mode == COMB:
            return (not self.q) or m_ready
        return self.rdy

    def clock(self, s_valid: bool, s_data: int, m_ready: bool):
        ready = self.s_ready(m_ready)
        if self.q and m_ready:                  # the head leaves
            self.q.pop(0)
        if s_valid and ready:
            self.q.append(s_data)
        assert len(self.q) <= self.cap, "model overflow"
        if self.mode != COMB:
            self.rdy = len(self.q) < self.cap


class Pipe:
    """N slices of one mode in series (or FWD: one shared-enable shift register of N stages). N = 0 is a wire."""

    def __init__(self, n: int, mode: int):
        self.n, self.mode = n, mode
        self.in_reset = True
        self.slices = [Slice(mode) for _ in range(n)] if mode != FWD else []
        self.st: list = [None] * n if mode == FWD else []      # FWD: stage contents (None = empty)

    def reset(self):
        for s in self.slices:
            s.reset()
        if self.mode == FWD:
            self.st = [None] * self.n

    def _readies(self, m_ready: bool) -> list[bool]:
        r = [False] * (self.n + 1)
        r[self.n] = m_ready
        for i in range(self.n - 1, -1, -1):
            r[i] = self.slices[i].s_ready(r[i + 1])
        return r

    def signals(self, m_ready: bool):
        """(s_ready, m_valid, m_data) in this clock, before the edge."""
        if self.n == 0:
            return m_ready, None, None            # wire: valid and data follow the inputs; the bench handles it
        if self.mode == FWD:
            en = m_ready or self.st[-1] is None
            return en, self.st[-1] is not None, self.st[-1]
        r = self._readies(m_ready)
        last = self.slices[-1]
        return r[0], last.m_valid(), last.m_data()

    def clock(self, s_valid: bool, s_data: int, m_ready: bool):
        if self.n == 0:
            return
        if self.mode == FWD:
            if m_ready or self.st[-1] is None:
                self.st = [s_data if s_valid else None] + self.st[:-1]
            return
        r = self._readies(m_ready)
        ins = []                                   # what each slice sees in this clock, taken before any state changes
        prev_v, prev_d = s_valid, s_data
        for i, s in enumerate(self.slices):
            ins.append((prev_v, prev_d, r[i + 1]))
            prev_v, prev_d = s.m_valid(), s.m_data()
        for s, (v, d, rr) in zip(self.slices, ins):
            s.clock(v, d, rr)


def latency(n: int, mode: int) -> int:
    """Clocks from the edge that accepts a beat into an empty chain to the first clock it is visible at m_*."""
    return n


def throughput(n: int, mode: int) -> Fraction:
    """Beats per clock with an always-valid source and an always-ready sink, in steady state."""
    return Fraction(1, 2) if (mode == HALF and n >= 1) else Fraction(1)


def capacity(n: int, mode: int) -> int:
    """Beats the chain holds when the sink stops and the source keeps offering, counted until s_ready first goes low
    for good (the beats accepted before and including the stall)."""
    if n == 0:
        return 0
    return 2 * n if mode in (SKID, FULL) else n


def ready_response(n: int, mode: int) -> int:
    """Clocks from m_ready rising (chain full, source offering) to s_ready rising: 0 when combinational; otherwise
    the models say: one clock per registered slice (1 for the head of the chain to free a place, then the ready
    register of every slice ahead of it is seen one clock later each)."""
    if n == 0 or mode in (FWD, COMB):
        return 0
    return n
