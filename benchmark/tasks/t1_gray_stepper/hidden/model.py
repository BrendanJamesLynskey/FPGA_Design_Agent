"""Golden model of t1_gray_stepper, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

GRAY, BIN, CTRL, RATE, STEPS = 0, 1, 2, 3, 4
DESIGN_ID = 0x47524159          # "GRAY"


def gray(b: int) -> int:
    return b ^ (b >> 1)


def ungray(g: int) -> int:
    b = 0
    while g:
        b ^= g
        g >>= 1
    return b


class Model:
    def __init__(self) -> None:
        self.bin = 0
        self.auto = 0
        self.rate = 250
        self.steps = 0
        self.dir = 0

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            self.bin = (self.bin + (-1 if self.dir else 1)) % 1024
            self.steps = (self.steps + 1) & 0xFFFF

    def next_gray(self, g: int) -> int:
        """The Gray code one step on from ``g`` in the current direction."""
        return gray((ungray(g) + (-1 if self.dir else 1)) % 1024)

    def read(self, off: int) -> int:
        return {GRAY: gray(self.bin), BIN: self.bin, CTRL: self.auto | self.dir << 8, RATE: self.rate,
                STEPS: self.steps}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == BIN:
            self.bin = v & 0x3FF
        elif off == CTRL:
            self.auto = v & 1
        elif off == RATE:
            self.rate = v & 0xFFFF

    def leds(self) -> int:
        return self.auto << 15 | gray(self.bin)
