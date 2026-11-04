"""Golden model of p_moving_avg, written from spec.yaml alone."""

from __future__ import annotations

SAMPLE, AVG, SUM, COUNT, CLIP, CTRL = range(6)
DESIGN_ID = 0x4D415647
WINDOW = 6


class Model:
    def __init__(self) -> None:
        self.win: list[int] = []
        self.last = 0
        self.clip = 500

    @property
    def avg(self) -> int:
        return sum(self.win) // len(self.win) if self.win else 0

    def push(self, s: int) -> None:
        s &= 0xFFF
        self.last = s
        if len(self.win) == WINDOW:
            a = self.avg
            s = max(0, min(4095, min(max(s, a - self.clip), a + self.clip)))
            self.win.pop(0)
        self.win.append(s)

    def read(self, off: int) -> int:
        return {SAMPLE: self.last, AVG: self.avg, SUM: sum(self.win), COUNT: len(self.win), CLIP: self.clip}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == SAMPLE:
            self.push(v)
        elif off == CLIP:
            self.clip = v & 0xFFF
        elif off == CTRL and v & 1:
            self.win = []

    def leds(self) -> int:
        return self.avg
