"""Golden model of p_seq_detect, written from spec.yaml alone."""

from __future__ import annotations

PATTERN, LEN, SHIFT, COUNT, SAMPLES, CTRL = range(6)
DESIGN_ID = 0x53514454


class Model:
    def __init__(self) -> None:
        self.pattern, self.len = 0x0B, 4
        self.shift = self.count = self.samples = 0
        self.match = False

    @property
    def len_e(self) -> int:
        return 1 if self.len == 0 else min(self.len, 8)

    def sample(self, bit: int, inv: int = 0) -> bool:
        """One sampling instant with HOLD = 0."""
        self.shift = ((self.shift << 1) | (bit & 1)) & 0xFF
        self.samples = (self.samples + 1) & 0xFFFF
        mask = (1 << self.len_e) - 1
        target = (~self.pattern & mask) if inv else (self.pattern & mask)
        n_since_clear = self.samples if self.samples else 0x10000
        self.match = n_since_clear >= self.len_e and (self.shift & mask) == target
        if self.match:
            self.count = (self.count + 1) & 0xFFFF
        return self.match

    def feed(self, bits: list[int], inv: int = 0) -> list[bool]:
        return [self.sample(b, inv) for b in bits]

    def read(self, off: int) -> int:
        return {PATTERN: self.pattern, LEN: self.len, SHIFT: self.shift, COUNT: self.count, SAMPLES: self.samples}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == PATTERN:
            self.pattern = v & 0xFF
        elif off == LEN:
            self.len = v & 0xF
        elif off == CTRL:
            self.shift = self.count = self.samples = 0
            self.match = False
