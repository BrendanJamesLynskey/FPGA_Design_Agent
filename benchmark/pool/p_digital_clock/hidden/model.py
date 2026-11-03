"""Golden model of p_digital_clock, written from spec.yaml alone."""

from __future__ import annotations

TIME, DAYS, UPTIME = 0, 1, 2
DESIGN_ID = 0x54434C4B
GLYPHS = ("abcdef", "bc", "abdeg", "abcdg", "bcfg", "acdfg", "acdefg", "abc", "abcdefg", "abcdfg")


def seg_pins(lit: str) -> int:
    return sum(0 if s in lit else 1 << i for i, s in enumerate("abcdefg"))


class Model:
    def __init__(self) -> None:
        self.h = self.m = self.s = 0
        self.days = 0
        self.uptime = 0
        self.twelve = False

    def seconds(self, k: int) -> None:
        for _ in range(k):
            self.uptime += 1
            self.s += 1
            if self.s == 60:
                self.s, self.m = 0, self.m + 1
                if self.m == 60:
                    self.m, self.h = 0, self.h + 1
                    if self.h == 24:
                        self.h = 0
                        self.days = (self.days + 1) & 0xFF

    def read(self, off: int) -> int:
        if off == TIME:
            return self.s | self.m << 6 | self.h << 12
        if off == DAYS:
            return self.days
        if off == UPTIME:
            return self.uptime
        return 0

    def write(self, off: int, v: int) -> None:
        if off == TIME:
            s, m, h = v & 63, (v >> 6) & 63, (v >> 12) & 31
            if s <= 59 and m <= 59 and h <= 23:
                self.s, self.m, self.h = s, m, h
        elif off == DAYS:
            self.days = 0

    def leds(self, pause: bool = False) -> int:
        return int(self.twelve and self.h >= 12) | int(pause) << 15

    def shown_hours(self) -> tuple[int, int]:
        h = (self.h % 12 or 12) if self.twelve else self.h
        return h // 10, h % 10

    def display(self) -> dict[int, tuple[int, int]]:
        """{digit: (segment pins, DP pin)} for the digits that are lit."""
        ht, hu = self.shown_hours()
        digs = {0: self.s % 10, 1: self.s // 10, 2: self.m % 10, 3: self.m // 10, 4: hu, 5: ht}
        out = {}
        for k, d in digs.items():
            if k == 5 and self.twelve and d == 0:
                continue
            out[k] = (seg_pins(GLYPHS[d]), 0 if k in (2, 4) else 1)
        return out
