"""Golden model of p_rr_arbiter, written from spec.yaml alone (clock-level; the RTL output may lag by a few clocks)."""

from __future__ import annotations

GRANTS0, GRANTS1, GRANTS2, GRANTS3, FORCED, LAST = 0, 1, 2, 3, 4, 5
DESIGN_ID = 0x52524152


class Model:
    def __init__(self, max_hold: int) -> None:
        self.max_hold = max_hold
        self.s1 = self.s2 = 0
        self.grant: int | None = None
        self.last = 3
        self.hold = 0
        self.grants = [0] * 4
        self.forced = 0

    def step(self, sw: int) -> int:
        """One clock with the raw request vector sw; returns the visible one-hot grant afterwards."""
        r = self.s2
        if self.grant is None:
            if r:
                for k in range(1, 5):
                    i = (self.last + k) % 4
                    if (r >> i) & 1:
                        self.grant, self.last, self.hold = i, i, 0
                        self.grants[i] = (self.grants[i] + 1) & 0xFFFF
                        break
        else:
            g = self.grant
            if not (r >> g) & 1:
                self.grant = None
            elif self.hold + 1 >= self.max_hold and r & ~(1 << g) & 0xF:
                self.grant = None
                self.forced = (self.forced + 1) & 0xFFFF
            else:
                self.hold += 1
        self.s2, self.s1 = self.s1, sw & 0xF
        return 0 if self.grant is None else 1 << self.grant

    def run(self, sws: list[int]) -> list[int]:
        return [self.step(s) for s in sws]

    def read(self, off: int) -> int:
        if off < 4:
            return self.grants[off]
        return {FORCED: self.forced, LAST: self.last}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == GRANTS0:
            self.grants = [0] * 4
            self.forced = 0
