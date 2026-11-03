"""Golden model of p_pulse_stretch, written from spec.yaml alone."""

from __future__ import annotations

TRIGGERS, RETRIGS, LONGEST, HOLD = 0, 1, 2, 3
DESIGN_ID = 0x50535452


class Model:
    def __init__(self, hold: int) -> None:
        self.hold = hold
        self.reset()

    def reset(self) -> None:
        self.triggers = 0
        self.retrigs = 0
        self.longest = 0
        self.pulses: list[list[int]] = []       # [start, end] per lit run (clock numbers)

    def lit_at(self, t: int) -> bool:
        return bool(self.pulses) and t < self.pulses[-1][1]

    def trigger(self, t: int) -> None:
        self.triggers = (self.triggers + 1) & 0xFFFF
        if self.lit_at(t):
            self.retrigs = (self.retrigs + 1) & 0xFFFF
            self.pulses[-1][1] = t + self.hold
        else:
            self.pulses.append([t, t + self.hold])
        self.longest = max(self.longest, self.pulses[-1][1] - self.pulses[-1][0])

    def run_lengths(self) -> list[int]:
        return [e - s for s, e in self.pulses]

    def read(self, off: int) -> int:
        return {TRIGGERS: self.triggers, RETRIGS: self.retrigs, LONGEST: self.longest, HOLD: self.hold}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == TRIGGERS:
            self.triggers = self.retrigs = self.longest = 0
            self.pulses = []
