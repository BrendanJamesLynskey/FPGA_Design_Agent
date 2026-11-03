"""Golden model of p_serial_divider, written from spec.yaml alone."""

from __future__ import annotations

NUM, DEN, CTRL, QUOT, REM, STATUS = range(6)
DESIGN_ID = 0x53444956


class Model:
    def __init__(self) -> None:
        self.num = self.den = 0
        self.quot = self.rem = 0
        self.divz = False
        self.done = False
        self.cycles = 0

    def start(self) -> None:
        n, d = self.num, self.den
        if d == 0:
            self.quot, self.rem, self.divz, self.cycles = 0xFFFF, n, True, 1
        elif d > n:
            self.quot, self.rem, self.divz, self.cycles = 0, n, False, 2
        else:
            self.quot, self.rem, self.divz, self.cycles = n // d, n % d, False, 17
        self.done = True

    def write(self, off: int, v: int) -> None:
        if off == NUM:
            self.num = v & 0xFFFF
        elif off == DEN:
            self.den = v & 0xFFFF
        elif off == CTRL and v & 1:
            self.start()

    def read(self, off: int) -> int:
        if off == NUM:
            return self.num
        if off == DEN:
            return self.den
        if off == QUOT:
            return self.quot
        if off == REM:
            return self.rem
        if off == STATUS:
            return int(self.done) << 1 | int(self.divz) << 2 | self.cycles << 8
        return 0

    def leds(self) -> int:
        return (self.quot & 0xFF) | int(self.divz) << 15
