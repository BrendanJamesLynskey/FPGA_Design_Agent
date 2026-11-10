"""Golden model of t2_sevenseg_marquee, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

DESIGN_ID = 0x4D415251
CTRL, LENGTH, POS, DIM, MSG0 = 0x00, 0x01, 0x02, 0x03, 0x10
SCROLL, DIR = 1, 2


class Model:
    def __init__(self) -> None:
        self.msg = [0] * 16
        self.ctrl, self.length, self.pos, self.dim = 0, 8, 0, 7

    def write(self, off: int, v: int) -> None:
        v &= 0xFFFF_FFFF
        if MSG0 <= off < MSG0 + 16:
            self.msg[off - MSG0] = v & 0xFF
        elif off == CTRL:
            self.ctrl = v & 3
        elif off == LENGTH:
            if 1 <= v <= 16:
                self.length = v
                if v <= self.pos:
                    self.pos = 0
        elif off == POS:
            if v < self.length:
                self.pos = v
        elif off == DIM:
            self.dim = v & 7

    def read(self, off: int) -> int:
        if MSG0 <= off < MSG0 + 16:
            return self.msg[off - MSG0]
        return {CTRL: self.ctrl, LENGTH: self.length, POS: self.pos, DIM: self.dim}.get(off, 0)

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            if self.ctrl & DIR:
                self.pos = (self.pos + self.length - 1) % self.length
            else:
                self.pos = (self.pos + 1) % self.length

    def digit_byte(self, k: int) -> int:
        return self.msg[(self.pos + 7 - k) % self.length]

    def display(self) -> dict[int, int]:
        """{digit: (DP..A pin levels, active low: 8 bits, bit 0 = CA, bit 7 = DP)}."""
        return {k: ~self.digit_byte(k) & 0xFF for k in range(8)}

    def lit_clocks(self, refresh_bits: int) -> int:
        return (self.dim + 1) << (refresh_bits - 3)
