"""Golden model of t1_press_classifier, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

SHORT_COUNT, LONG_COUNT, LAST, STATUS = 0, 1, 2, 3
DESIGN_ID = 0x50525343          # "PRSC"


class Model:
    def __init__(self, long_cycles: int, tick_cycles: int) -> None:
        self.long_cycles, self.tick = long_cycles, tick_cycles
        self.short = self.long = 0
        self.last = self.last_long = 0
        self.led0 = self.led1 = 0

    def press(self, h: int) -> None:
        """A clean press whose debounced level is high for ``h`` clocks, then released."""
        is_long = h >= self.long_cycles
        self.last = min(h // self.tick, 0xFFFF)
        self.last_long = int(is_long)
        if is_long:
            self.long = (self.long + 1) & 0xFFFF
            self.led1 ^= 1
        else:
            self.short = (self.short + 1) & 0xFFFF
            self.led0 ^= 1

    def read(self, off: int, level: int = 0) -> int:
        if off == SHORT_COUNT:
            return self.short
        if off == LONG_COUNT:
            return self.long
        if off == LAST:
            return self.last | self.last_long << 16
        if off == STATUS:
            return level | self.led0 << 1 | self.led1 << 2
        return 0

    def write(self, off: int, v: int) -> None:
        if off == SHORT_COUNT:
            self.short = 0
        elif off == LONG_COUNT:
            self.long = 0

    def leds(self) -> int:
        return (self.short & 0xFF) << 8 | self.led1 << 1 | self.led0
