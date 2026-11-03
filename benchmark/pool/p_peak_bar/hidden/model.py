"""Golden model of p_peak_bar, written from spec.yaml alone."""

from __future__ import annotations

LEVEL, PEAK, MAXRAW = 0, 1, 2
DESIGN_ID = 0x504B4252


def bar_len(raw: int) -> int:
    return (raw + 15) // 16


class Model:
    def __init__(self) -> None:
        self.raw = 0
        self.peak = 0
        self.maxraw = 0

    @property
    def n(self) -> int:
        return bar_len(self.raw)

    def level(self, raw: int) -> None:
        self.raw = raw & 0xFF
        self.peak = max(self.peak, self.n)
        self.maxraw = max(self.maxraw, self.raw)

    def clear_peak(self) -> None:
        self.peak = self.n

    def decay_step(self) -> None:
        if self.peak > self.n:
            self.peak -= 1

    def leds(self) -> int:
        return ((1 << self.n) - 1) | ((1 << (self.peak - 1)) if self.peak else 0)

    def decay_leds(self) -> list[int]:
        """The LED words after each successive marker step, from now until the marker meets the bar."""
        out, save = [], self.peak
        while self.peak > self.n:
            self.decay_step()
            out.append(self.leds())
        self.peak = save
        return out

    def read(self, off: int) -> int:
        return {LEVEL: self.n, PEAK: self.peak, MAXRAW: self.maxraw}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == MAXRAW:
            self.maxraw = self.raw
