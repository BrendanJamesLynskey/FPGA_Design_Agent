"""Golden model of p_sat_accum, written from spec.yaml alone."""

from __future__ import annotations

ACC, FLAGS, ADDS, LIMIT = 0, 1, 2, 3
DESIGN_ID = 0x53415441


def signed(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


class Model:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.acc = 0
        self.hi = self.lo = False
        self.adds = 0

    def tick(self, sw: int) -> None:
        """One tick with FREEZE and CLEAR down; sw is SW[7:0]."""
        s = self.acc + signed(sw, 8)
        if s > self.limit:
            s, self.hi = self.limit, True
        elif s < -self.limit:
            s, self.lo = -self.limit, True
        self.acc = s
        self.adds = (self.adds + 1) & 0xFFFF

    def clear_level(self) -> None:
        self.acc = 0

    def leds(self) -> int:
        return self.acc & 0xFFFF

    def read(self, off: int) -> int:
        if off == ACC:
            return self.acc & 0xFFFFFFFF
        if off == FLAGS:
            return int(self.hi) | int(self.lo) << 1
        if off == ADDS:
            return self.adds
        if off == LIMIT:
            return self.limit
        return 0

    def write(self, off: int, v: int) -> None:
        if off == ACC:
            self.acc = max(-self.limit, min(self.limit, signed(v, 16)))
        elif off == FLAGS:
            self.hi = self.lo = False
        elif off == ADDS:
            self.adds = 0
