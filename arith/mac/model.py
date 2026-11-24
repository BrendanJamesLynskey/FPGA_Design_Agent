"""Bit-exact, cycle-accurate model of the multiply-accumulate (arith/mac/spec.md), brief 139a.

``MacModel(wa, wb, lanes, accw, signed, lat)``: ``step(rst, en, clr, a, b)`` is one rising clock edge with those inputs (a and b are the packed lane
vectors) and returns the accumulator value visible after the edge. The pipeline is a delay line of ``lat - 1`` samples in front of the clock where a
sample is added: a sample presented at edge t is in the accumulator after edge t + lat - 1 (so lat 1 means the same edge). ``rst`` clears the
accumulator and every sample in the delay line, and the sample presented on the same edge. The arithmetic is Python's integers; ``dot`` gives the
lane sum alone, which the model's own tests compare with a plain loop."""
from __future__ import annotations

from collections import deque


def to_signed(x: int, w: int) -> int:
    return x - (1 << w) if x >> (w - 1) else x


def lanes_of(packed: int, w: int, n: int) -> list[int]:
    return [(packed >> (k * w)) & ((1 << w) - 1) for k in range(n)]


def dot(wa: int, wb: int, lanes: int, signed: int, a: int, b: int) -> int:
    """The sum over the lanes of the products of a's and b's lane values (an exact integer; negative when signed)."""
    tot = 0
    for x, y in zip(lanes_of(a, wa, lanes), lanes_of(b, wb, lanes)):
        tot += (to_signed(x, wa) * to_signed(y, wb)) if signed else x * y
    return tot


class MacModel:
    def __init__(self, wa: int, wb: int, lanes: int, accw: int, signed: int, lat: int):
        assert lat >= 1 and accw >= wa + wb
        self.wa, self.wb, self.lanes, self.accw, self.signed, self.lat = wa, wb, lanes, accw, signed, lat
        self.acc = 0
        self.pipe: deque = deque([None] * (lat - 1), maxlen=max(lat - 1, 1))

    def step(self, rst: int, en: int, clr: int, a: int, b: int) -> int:
        if rst:
            self.acc = 0
            self.pipe = deque([None] * (self.lat - 1), maxlen=max(self.lat - 1, 1))
            return self.acc
        new = (clr, dot(self.wa, self.wb, self.lanes, self.signed, a, b)) if en else None
        if self.lat == 1:
            out = new
        else:
            out = self.pipe[-1]
            self.pipe.appendleft(new)
        if out is not None:
            c, prod = out
            self.acc = ((0 if c else self.acc) + prod) % (1 << self.accw)
        return self.acc


LATENCY = {"dsp": lambda p: p["NREG"], "dsp_cascade": lambda p: p["LANES"] + 1, "fabric": lambda p: p["NREG"]}
