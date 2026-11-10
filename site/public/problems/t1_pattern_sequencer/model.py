"""Golden model of t1_pattern_sequencer, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

CTRL, LENGTH, INDEX, STATUS, LOOPS = range(5)
ENTRY0 = 0x10
DESIGN_ID = 0x50534551          # "PSEQ"


class Model:
    def __init__(self, tick: int) -> None:
        self.tick = tick
        self.pat = [0] * 16
        self.dur = [0] * 16
        self.length = 4
        self.oneshot = 0

    def write(self, off: int, v: int) -> None:
        if ENTRY0 <= off < ENTRY0 + 16:
            self.pat[off - ENTRY0] = v & 0xFFFF
            self.dur[off - ENTRY0] = (v >> 16) & 0xFF
        elif off == LENGTH and 1 <= (v & 0x1F) <= 16:
            self.length = v & 0x1F
        elif off == CTRL:
            self.oneshot = (v >> 1) & 1

    def read_entry(self, i: int) -> int:
        return self.pat[i] | self.dur[i] << 16

    def clocks(self, i: int) -> int:
        return (self.dur[i] or 256) * self.tick

    def show(self, n: int) -> list[tuple[int, int]]:
        """The first n (pattern, clocks shown) of a playback started now, with no pause and no writes."""
        out, i = [], 0
        while len(out) < n:
            out.append((self.pat[i], self.clocks(i)))
            i += 1
            if i >= self.length:
                if self.oneshot:
                    break
                i = 0
        return out
