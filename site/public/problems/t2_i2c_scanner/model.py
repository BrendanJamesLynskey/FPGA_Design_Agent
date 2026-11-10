"""Golden model of t2_i2c_scanner, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

DESIGN_ID = 0x5343414E
CTRL, STATUS, COUNT, LOWEST, MAP0 = 0, 1, 2, 3, 4
BUSY, DONE = 1, 2
FIRST, LAST = 0x08, 0x77


class Model:
    def __init__(self) -> None:
        self.map = 0
        self.count = 0
        self.lowest = 0xFF
        self.done = False

    def scan(self, present: set[int]) -> list[tuple]:
        """A complete scan over a bus where ``present`` ACK; returns the bus log it must produce."""
        self.map, self.count, self.lowest = 0, 0, 0xFF
        log: list[tuple] = []
        for a in range(FIRST, LAST + 1):
            ack = a in present
            log += [("S",), ("A", a, 0, ack), ("P",)]
            if ack:
                self.map |= 1 << a
                self.count += 1
                if self.lowest == 0xFF:
                    self.lowest = a
        self.done = True
        return log

    def read(self, off: int) -> int:
        if off == STATUS:
            return DONE if self.done else 0
        if off == COUNT:
            return self.count
        if off == LOWEST:
            return self.lowest
        if MAP0 <= off <= MAP0 + 3:
            return (self.map >> (32 * (off - MAP0))) & 0xFFFF_FFFF
        return 0

    def leds(self) -> int:
        return self.count
