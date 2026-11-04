"""Golden model of p_quad_decoder, written from spec.yaml alone."""

from __future__ import annotations

POS, FWD, REV, ERRS, DIR = 0, 1, 2, 3, 4
DESIGN_ID = 0x51444543
GRAY = {0b00: 0, 0b01: 1, 0b11: 2, 0b10: 3}


class Model:
    def __init__(self, ab: int = 0) -> None:
        self.ab = ab
        self.idx = 0
        self.pos = self.fwd = self.rev = self.errs = self.dir = 0

    def set_ab(self, ab: int) -> None:
        d = (GRAY[ab] - GRAY[self.ab]) % 4
        self.ab = ab
        if d == 1:
            self.pos, self.fwd, self.dir = (self.pos + 1) & 0xFFFF, (self.fwd + 1) & 0xFFFF, 1
        elif d == 3:
            self.pos, self.rev, self.dir = (self.pos - 1) & 0xFFFF, (self.rev + 1) & 0xFFFF, 2
        elif d == 2:
            self.errs = min(255, self.errs + 1)

    def index(self) -> None:
        self.pos = 0

    def read(self, off: int) -> int:
        return {POS: self.pos, FWD: self.fwd, REV: self.rev, ERRS: self.errs, DIR: self.dir}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == POS:
            self.pos = v & 0xFFFF
        elif off == FWD:
            self.fwd = 0
        elif off == REV:
            self.rev = 0
        elif off == ERRS:
            self.errs = 0

    def leds(self) -> int:
        return self.pos
