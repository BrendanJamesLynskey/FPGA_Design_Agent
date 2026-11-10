"""Golden model of v2_a_seq_detect, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

COUNT, LEVEL = 0, 1
DESIGN_ID = 0x53514454          # "SQDT"
PATTERN = (1, 0, 1, 1)           # oldest first
LATENCY = 2                      # LED[0] follows the bit by two clocks


class Model:
    def __init__(self) -> None:
        self.hist = [0, 0, 0, 0]
        self.count = 0

    def push(self, bit: int) -> int:
        """Take one bit in; the return value is HIT for that bit (it shows on LED[0] LATENCY clocks later)."""
        self.hist = self.hist[1:] + [bit]
        hit = int(tuple(self.hist) == PATTERN)
        self.count = (self.count + hit) & 0xFFFF
        return hit

    def stream(self, bits) -> list[int]:
        return [self.push(b) for b in bits]

    def clear(self) -> None:
        self.count = 0

    def read(self, off: int, level: int = 0) -> int:
        return {COUNT: self.count, LEVEL: level}.get(off, 0)
