"""Golden model of v2_a_bit_count, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

WORD, POP, LZC, REV = range(4)
DESIGN_ID = 0x42434E54          # "BCNT"
M = 0xFFFFFFFF


def pop(w: int) -> int:
    return bin(w & M).count("1")


def lzc(w: int) -> int:
    return 32 - (w & M).bit_length()


def rev(w: int) -> int:
    return int(format(w & M, "032b")[::-1], 2)


class Model:
    def __init__(self) -> None:
        self.w = 0

    def write(self, off: int, v: int) -> None:
        if off == WORD:
            self.w = v & M

    def read(self, off: int) -> int:
        return {WORD: self.w, POP: pop(self.w), LZC: lzc(self.w), REV: rev(self.w)}.get(off, 0)

    def leds(self) -> int:
        return pop(self.w)
