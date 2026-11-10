"""Golden model of t1_lfsr_dice, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

STATE, SEED, TAPS, ROLL, HISTORY, STEP, ROLLS = range(7)
DESIGN_ID = 0x44494345          # "DICE"
GLYPHS = {1: "bc", 2: "abdeg", 3: "abcdg", 4: "bcfg", 5: "acdfg", 6: "acdefg"}


def seg_pins(lit: str) -> int:
    """Active-low CA..CG, bit 0 = CA."""
    return sum(0 if s in lit else 1 << i for i, s in enumerate("abcdefg"))


def lstep(s: int, taps: int) -> int:
    b = s & 1
    s >>= 1
    if b:
        s ^= taps
    return s or 1


class Model:
    def __init__(self) -> None:
        self.s = self.seed = 0xACE1
        self.taps = 0xB400
        self.roll = self.hist = self.rolls = 0

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            self.s = lstep(self.s, self.taps)

    def press(self) -> None:
        self.step()
        self.roll = self.s % 6 + 1
        self.hist = (self.hist << 4 | self.roll) & 0xFFFF
        self.rolls = (self.rolls + 1) & 0xFFFF

    def read(self, off: int) -> int:
        return {STATE: self.s, SEED: self.seed, TAPS: self.taps, ROLL: self.roll, HISTORY: self.hist,
                STEP: 0, ROLLS: self.rolls}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == SEED:
            self.seed = v & 0xFFFF
            self.s = self.seed or 1
        elif off == TAPS:
            self.taps = v & 0xFFFF
        elif off == STEP:
            self.step(v & 0xFFFF)          # the burst, once it has finished

    def display(self) -> dict[int, int]:
        return {0: seg_pins(GLYPHS[self.roll])} if self.roll else {}
