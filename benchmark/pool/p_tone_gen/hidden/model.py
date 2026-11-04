"""Golden model of p_tone_gen, written from spec.yaml alone."""

from __future__ import annotations

NOTE, HALF, TOGGLES = 0, 1, 2
DESIGN_ID = 0x544F4E45
WEIGHT = (24, 22, 20, 18, 16, 15, 13, 12)


def half_period(base: int, note: int, octave: int) -> int:
    h = base * WEIGHT[note & 7] // 12
    return h >> 1 if octave else h


class Model:
    def __init__(self, base: int) -> None:
        self.base = base
        self.sw = 0
        self.toggles = 0

    @property
    def note(self) -> int:
        return self.sw & 7

    @property
    def octave(self) -> int:
        return (self.sw >> 3) & 1

    @property
    def half(self) -> int:
        return half_period(self.base, self.note, self.octave)

    def read(self, off: int) -> int:
        if off == NOTE:
            return self.octave << 3 | self.note
        if off == HALF:
            return self.half
        if off == TOGGLES:
            return self.toggles
        return 0

    def write(self, off: int, v: int) -> None:
        if off == TOGGLES:
            self.toggles = 0

    def leds(self) -> int:
        return self.note | self.octave << 3 | (1 << 15 if self.sw & 0x8000 else 0)
