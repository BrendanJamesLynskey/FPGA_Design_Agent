"""Golden model of p_hcsr04, written from spec.yaml alone."""

from __future__ import annotations

START, RAW, DIST, WIDTH, GOOD, TIMEOUTS, OOR, STATUS, CTRL = range(9)
DESIGN_ID = 0x48435352


def median(vals: list[int]) -> int:
    v = sorted(vals)
    return v[0] if len(v) == 1 else (v[0] if len(v) == 2 else v[1])


class Model:
    def __init__(self, clks_per_cm: int, max_echo: int) -> None:
        self.cpc, self.max_echo = clks_per_cm, max_echo
        self.window: list[int] = []
        self.raw = self.dist = self.width = 0
        self.good = self.timeouts = self.oor = 0

    def ping(self, echo_width: int | None) -> str:
        """One completed ping against an echo of the given width in clocks (None: no echo)."""
        if echo_width is None:
            self.timeouts = (self.timeouts + 1) & 0xFFFF
            return "timeout"
        if echo_width > self.max_echo:
            self.oor = (self.oor + 1) & 0xFFFF
            return "oor"
        self.width = echo_width
        self.raw = echo_width // self.cpc
        self.good = (self.good + 1) & 0xFFFF
        self.window = (self.window + [self.raw])[-3:]
        self.dist = median(self.window)
        return "good"

    def read(self, off: int) -> int:
        return {RAW: self.raw, DIST: self.dist, WIDTH: self.width, GOOD: self.good, TIMEOUTS: self.timeouts, OOR: self.oor}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == CTRL:
            self.window = []
            self.raw = self.dist = self.width = 0
            self.good = self.timeouts = self.oor = 0

    def leds(self) -> int:
        return min(self.dist, 255)
