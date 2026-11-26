"""Cycle-accurate golden model for ip_lib/credit_chan, written from the definition of credit-based flow control.

A sender holds `credits`, starts with CREDITS and spends one per beat sent; the beat crosses LF register stages and
enters a receiver buffer of CREDITS entries; every beat the receiver's output gives away sends one credit back through
LB register stages. The sender may send only while it holds a credit; the ready signal is a register that follows
"credits > 0 after the previous edge" (low in reset and for the first clock after). The receiver's valid is a register
that follows "buffer not empty after the previous edge". `step`-style use: `signals(m_ready)` gives what is visible in
a clock before the edge, `clock(...)` advances over the edge.
Declared figures: `latency`, `rtt`, `throughput`, `capacity`.
"""
from __future__ import annotations

from fractions import Fraction


class Chan:
    def __init__(self, credits: int, lf: int, lb: int):
        self.c, self.lf, self.lb = credits, lf, lb
        self.reset()

    def reset(self):
        self.credits = self.c
        self.ready = False
        self.fwd = [None] * self.lf            # beats on the forward stages (stage 1 first)
        self.buf: list[int] = []               # the receiver buffer
        self.ret = [False] * self.lb           # credits on the return stages (stage 1 first)

    def signals(self, m_ready: bool):
        return self.ready, bool(self.buf), (self.buf[0] if self.buf else None)

    def clock(self, s_valid: bool, s_data: int, m_ready: bool):
        send = s_valid and self.ready
        pop = bool(self.buf) and m_ready
        credit_in = self.ret[-1] if self.lb else pop
        arriving = self.fwd[-1] if self.lf else (s_data if send else None)
        if pop:
            self.buf.pop(0)
        if arriving is not None:
            self.buf.append(arriving)
        assert len(self.buf) <= self.c, "model: receiver buffer overflow"
        self.credits += int(credit_in) - int(send)
        assert 0 <= self.credits <= self.c
        self.ready = self.credits > 0
        if self.lf:
            self.fwd = [s_data if send else None] + self.fwd[:-1]
        if self.lb:
            self.ret = [pop] + self.ret[:-1]


def latency(credits: int, lf: int, lb: int) -> int:
    """Clocks from the edge that accepts a beat (empty channel) to the first clock it is visible at m_*."""
    return lf + 1


def rtt(credits: int, lf: int, lb: int) -> int:
    """Credit round trip: a beat sent at edge t gives its credit back (sink always ready) in time for a beat sent at edge t + rtt."""
    return lf + lb + 2


def throughput(credits: int, lf: int, lb: int) -> Fraction:
    """Beats per clock, always-valid source, always-ready sink, steady state."""
    return min(Fraction(1), Fraction(credits, rtt(credits, lf, lb)))


def capacity(credits: int, lf: int, lb: int) -> int:
    """Beats accepted with the sink stopped (the receiver buffer is the only storage that fills)."""
    return credits


def min_credits_full_rate(lf: int, lb: int) -> int:
    return rtt(0, lf, lb)
