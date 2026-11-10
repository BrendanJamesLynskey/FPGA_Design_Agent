"""Golden model of v2_a_shifter, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

A, CTRL, RES = 0, 1, 2
DESIGN_ID = 0x53484654          # "SHFT"
M = 0xFFFFFFFF


def shift(a: int, amt: int, mode: int) -> int:
    a &= M
    if mode == 0:
        return (a << amt) & M if amt < 32 else 0
    if mode == 1:
        return a >> amt if amt < 32 else 0
    if mode == 2:
        signed = a - (1 << 32) if a >> 31 else a
        return (signed >> min(amt, 31)) & M
    r = amt % 32
    return ((a << r) | (a >> (32 - r))) & M


class Model:
    def __init__(self) -> None:
        self.a, self.amt, self.mode = 0, 0, 0

    def write(self, off: int, v: int) -> None:
        if off == A:
            self.a = v & M
        elif off == CTRL:
            self.amt, self.mode = v & 0x3F, v >> 8 & 3

    def res(self) -> int:
        return shift(self.a, self.amt, self.mode)

    def read(self, off: int) -> int:
        return {A: self.a, CTRL: self.mode << 8 | self.amt, RES: self.res()}.get(off, 0)

    def leds(self) -> int:
        return self.res() & 0xFFFF
