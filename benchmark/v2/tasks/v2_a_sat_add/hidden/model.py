"""Golden model of v2_a_sat_add, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

A, B, CTRL, SUM, FLAGS = range(5)
DESIGN_ID = 0x53414444          # "SADD"


def add(a: int, b: int, signed: int, sat: int) -> tuple[int, int]:
    """(SUM, FLAGS) for 16-bit operands."""
    a, b = a & 0xFFFF, b & 0xFFFF
    raw = a + b
    wrapped = raw & 0xFFFF
    if signed:
        ovf = int((a >> 15) == (b >> 15) and (wrapped >> 15) != (a >> 15))
    else:
        ovf = raw >> 16
    s = wrapped
    if sat and ovf:
        s = (0x8000 if a >> 15 else 0x7FFF) if signed else 0xFFFF
    return s, ovf | int(s == 0) << 1 | (s >> 15) << 2


class Model:
    def __init__(self) -> None:
        self.a = self.b = self.signed = self.sat = 0

    def write(self, off: int, v: int) -> None:
        if off == A:
            self.a = v & 0xFFFF
        elif off == B:
            self.b = v & 0xFFFF
        elif off == CTRL:
            self.signed, self.sat = v & 1, v >> 1 & 1

    def result(self) -> tuple[int, int]:
        return add(self.a, self.b, self.signed, self.sat)

    def read(self, off: int) -> int:
        s, f = self.result()
        return {A: self.a, B: self.b, CTRL: self.signed | self.sat << 1, SUM: s, FLAGS: f}.get(off, 0)
