"""Golden model of p_servo_rx, written from spec.yaml alone."""

from __future__ import annotations

WIDTH, POS, STATUS, GOOD, BAD, CTRL = range(6)
DESIGN_ID = 0x53525652


class Model:
    def __init__(self, min_w: int, max_w: int, vmin: int, vmax: int) -> None:
        self.min_w, self.max_w, self.vmin, self.vmax = min_w, max_w, vmin, vmax
        self.width = 0
        self.stored = 128
        self.fail = False
        self.lastgood = False
        self.good = self.bad = 0

    def position(self, w: int) -> int:
        if w <= self.min_w:
            return 0
        if w >= self.max_w:
            return 255
        return (w - self.min_w) * 255 // (self.max_w - self.min_w)

    def pulse(self, w: int) -> bool:
        self.width = w
        if self.vmin <= w <= self.vmax:
            self.good = (self.good + 1) & 0xFFFF
            self.lastgood, self.fail = True, False
            self.stored = self.position(w)
            return True
        self.bad = (self.bad + 1) & 0xFFFF
        self.lastgood = False
        return False

    def timeout(self) -> None:
        self.fail = True
        self.stored = 128

    @property
    def pos(self) -> int:
        return 128 if self.fail else self.stored

    def read(self, off: int) -> int:
        return {WIDTH: self.width, POS: self.pos, STATUS: int(self.fail) | int(self.lastgood) << 1, GOOD: self.good, BAD: self.bad}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == CTRL:
            self.good = self.bad = 0

    def leds(self) -> int:
        return self.pos | int(self.lastgood) << 14 | int(self.fail) << 15
