"""Golden model of p_adt7420_oneshot, written from spec.yaml alone."""

from __future__ import annotations

CTRL, RES, STATUS, RAW, TEMP, MIN, MAX, COUNT, ERRORS = range(9)
DESIGN_ID = 0x54374F53


def signed16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def config_byte(res16: bool) -> int:
    return 0x20 | (0x80 if res16 else 0)


class Model:
    def __init__(self) -> None:
        self.res = 0
        self.busy = False
        self.done = False
        self.fail = False
        self.ignored = 0
        self.raw = 0
        self.temp = 0
        self.min, self.max = 0x7FFF, 0x8000
        self.count = 0
        self.errors = 0
        self.clear_minmax()

    def clear_minmax(self) -> None:
        self.min_s, self.max_s = None, None
        self.count = 0
        self.errors = 0

    def start(self) -> bool:
        if self.busy:
            self.ignored = min(255, self.ignored + 1)
            return False
        self.busy, self.done = True, False
        return True

    def complete(self, raw: int) -> None:
        self.busy, self.done, self.fail = False, True, False
        self.raw = raw & 0xFFFF
        t = signed16(raw) >> 3
        self.temp = t & 0xFFFF
        self.min_s = t if self.min_s is None else min(self.min_s, t)
        self.max_s = t if self.max_s is None else max(self.max_s, t)
        self.count = (self.count + 1) & 0xFFFF

    def abandon(self) -> None:
        self.busy, self.done, self.fail = False, True, True
        self.errors = min(255, self.errors + 1)

    def read(self, off: int) -> int:
        if off == RES:
            return self.res
        if off == STATUS:
            return int(self.busy) | int(self.done) << 1 | int(self.fail) << 2 | self.ignored << 8
        if off == RAW:
            return self.raw
        if off == TEMP:
            return self.temp
        if off == MIN:
            return 0x7FFF if self.min_s is None else self.min_s & 0xFFFF
        if off == MAX:
            return 0x8000 if self.max_s is None else self.max_s & 0xFFFF
        if off == COUNT:
            return self.count
        if off == ERRORS:
            return self.errors
        return 0

    def write(self, off: int, v: int) -> None:
        if off == RES:
            self.res = v & 1
        elif off == CTRL and v & 2:
            self.clear_minmax()

    def leds(self) -> int:
        return self.temp
