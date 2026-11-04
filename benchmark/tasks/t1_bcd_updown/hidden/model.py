"""Golden model of t1_bcd_updown, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

STEPS = (1, 2, 5, 10)
COUNT, BCD, WRAPS, STEP = 0, 1, 2, 3
DESIGN_ID = 0x42434455
GLYPHS = ("abcdef", "bc", "abdeg", "abcdg", "bcfg", "acdfg", "acdefg", "abc", "abcdefg", "abcdfg")


def seg_pins(lit: str) -> int:
    """Active-low CA..CG, bit 0 = CA."""
    return sum(0 if s in lit else 1 << i for i, s in enumerate("abcdefg"))


class Model:
    def __init__(self) -> None:
        self.count = 0
        self.wraps = 0
        self.sw = 0

    @property
    def step(self) -> int:
        return STEPS[self.sw & 3]

    def press(self, up: bool = False, down: bool = False) -> None:
        if up and down:
            return
        if up:
            n = self.count + self.step
        elif down:
            n = self.count - self.step
        else:
            return
        if n >= 10000 or n < 0:
            self.wraps = (self.wraps + 1) & 0xFF
        self.count = n % 10000

    def read(self, off: int) -> int:
        if off == COUNT:
            return self.count
        if off == BCD:
            return sum(((self.count // 10 ** k) % 10) << (4 * k) for k in range(4))
        if off == WRAPS:
            return self.wraps
        if off == STEP:
            return self.step
        return 0

    def write(self, off: int, v: int) -> None:
        if off == COUNT and v < 10000:
            self.count = v
        elif off == WRAPS:
            self.wraps = 0

    def leds(self) -> int:
        return self.count & 0x3FFF

    def display(self) -> dict[int, int]:
        """{digit: active-low segments} for the digits that are lit; absent digits are dark."""
        out = {0: seg_pins(GLYPHS[self.count % 10])}
        for k in range(1, 4):
            if self.count >= 10 ** k:
                out[k] = seg_pins(GLYPHS[(self.count // 10 ** k) % 10])
        return out
