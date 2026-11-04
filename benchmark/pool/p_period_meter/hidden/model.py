"""Golden model of p_period_meter, written from spec.yaml alone."""

from __future__ import annotations

LAST, MIN, MAX, COUNT, STALLED, CTRL = range(6)
DESIGN_ID = 0x5052444D


class Model:
    def __init__(self, timeout: int) -> None:
        self.timeout = timeout
        self.stalled = False
        self.have_edge = False
        self.clear()

    def clear(self) -> None:
        self.last = 0
        self.min = 0xFFFFFFFF
        self.max = 0
        self.count = 0
        self.have_edge = False

    def edge(self, dt: int | None) -> None:
        """An edge `dt` clocks after the previous one (None for the first)."""
        if dt is not None and dt > self.timeout:
            self.stalled = True                  # the gap exceeded the limit while waiting
        if not self.have_edge or self.stalled:
            self.stalled = False
            self.have_edge = True
            return
        self.last = dt
        self.min = min(self.min, dt)
        self.max = max(self.max, dt)
        self.count = (self.count + 1) & 0xFFFF

    def timed_out(self) -> None:
        """No edge for more than TIMEOUT_PERIOD clocks."""
        self.stalled = True

    def read(self, off: int) -> int:
        return {LAST: self.last, MIN: self.min, MAX: self.max, COUNT: self.count, STALLED: int(self.stalled)}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == CTRL:
            self.clear()

    def leds(self) -> int:
        return min(self.last, 0xFFFF)
