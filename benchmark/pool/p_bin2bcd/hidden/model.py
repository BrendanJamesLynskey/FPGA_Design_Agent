"""Golden model of p_bin2bcd, written from spec.yaml alone."""

from __future__ import annotations

IN, BCD, STATUS = 0, 1, 2
DESIGN_ID = 0x42324244
GLYPHS = ("abcdef", "bc", "abdeg", "abcdg", "bcfg", "acdfg", "acdefg", "abc", "abcdefg", "abcdfg")


def seg_pins(lit: str) -> int:
    return sum(0 if s in lit else 1 << i for i, s in enumerate("abcdefg"))


class Model:
    def __init__(self) -> None:
        self.inp = 0

    def write(self, off: int, v: int) -> None:
        if off == IN:
            self.inp = v & 0x8001FFFF

    @property
    def mag(self) -> int:
        return self.inp & 0x1FFFF

    @property
    def ovf(self) -> bool:
        return self.mag > 99999

    @property
    def digits_value(self) -> int:
        return 99999 if self.ovf else self.mag

    @property
    def neg(self) -> bool:
        return bool(self.inp >> 31) and self.digits_value != 0

    def bcd(self) -> int:
        v = self.digits_value
        return sum(((v // 10 ** k) % 10) << (4 * k) for k in range(5))

    def read(self, off: int) -> int:
        if off == IN:
            return self.inp
        if off == BCD:
            return self.bcd()
        if off == STATUS:
            return int(self.ovf) | int(self.neg) << 1
        return 0

    def leds(self) -> int:
        return self.bcd() & 0xFFFF

    def display(self) -> dict[int, int]:
        v = self.digits_value
        n = len(str(v))
        out = {k: seg_pins(GLYPHS[(v // 10 ** k) % 10]) for k in range(n)}
        if self.neg:
            out[n] = seg_pins("g")
        if self.ovf:
            out[6] = seg_pins("adefg")
        return out
