"""Golden model of p_stepper_ramp, written from spec.yaml alone."""

from __future__ import annotations

MOVE, POSITION, STATUS = 0, 1, 2
DESIGN_ID = 0x53544550


def gaps(n: int, start: int, minimum: int, dec: int) -> list[int]:
    """Start-to-start spacing between consecutive steps of an n-step move (n - 1 values)."""
    out = []
    for k in range(n - 1):
        acc = max(minimum, start - k * dec)
        decel = max(minimum, start - (n - 2 - k) * dec)
        out.append(max(acc, decel))
    return out


def step_starts(n: int, setup: int, start: int, minimum: int, dec: int) -> list[int]:
    """Clock of each step start, relative to the move start clock."""
    t = setup
    out = [t]
    for g in gaps(n, start, minimum, dec):
        t += g
        out.append(t)
    return out


def signed16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class Model:
    def __init__(self) -> None:
        self.pos = 0
        self.busy = False
        self.refused = self.moves = 0
        self.dir = 0

    def write(self, off: int, v: int) -> None:
        if off == MOVE:
            n = signed16(v)
            if n == 0:
                return
            if self.busy:
                self.refused = min(255, self.refused + 1)
                return
            self.busy = True
            self.moves = (self.moves + 1) & 0xFF
            self.dir = 1 if n > 0 else 0
            self.pos += n
        elif off == POSITION and not self.busy:
            v &= 0xFFFFFFFF
            self.pos = v - (1 << 32) if v & 0x80000000 else v

    def finish(self) -> None:
        self.busy = False

    def read(self, off: int) -> int:
        if off == POSITION:
            return self.pos & 0xFFFFFFFF
        if off == STATUS:
            return int(self.busy) | self.refused << 8 | self.moves << 16
        return 0
