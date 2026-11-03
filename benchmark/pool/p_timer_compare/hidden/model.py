"""Golden model of p_timer_compare, written from spec.yaml alone (tick level)."""

from __future__ import annotations

CTRL, PRESC, CNT, CMPA, CMPB, FLAGS = range(6)
DESIGN_ID = 0x544D5243
NONE, SET, CLEAR, TOGGLE = range(4)


class Model:
    def __init__(self) -> None:
        self.ctrl = 0
        self.presc = 0
        self.cnt = 0
        self.cmpa = self.cmpb = 0xFFFFFFFF
        self.flags = 0
        self.out = [0, 0]

    @property
    def run(self) -> bool:
        return bool(self.ctrl & 1)

    @property
    def arl(self) -> bool:
        return bool(self.ctrl & 2)

    def _act(self, ch: int, mode: int) -> None:
        if mode == SET:
            self.out[ch] = 1
        elif mode == CLEAR:
            self.out[ch] = 0
        elif mode == TOGGLE:
            self.out[ch] ^= 1

    def tick(self) -> tuple[bool, bool]:
        """One prescaler tick (RUN = 1). Returns (match A, match B)."""
        nxt = 0 if (self.arl and self.cnt == self.cmpa) else (self.cnt + 1) & 0xFFFFFFFF
        self.cnt = nxt
        ma, mb = nxt == self.cmpa, nxt == self.cmpb
        if ma:
            self.flags |= 1
            self._act(0, (self.ctrl >> 2) & 3)
        if mb:
            self.flags |= 2
            self._act(1, (self.ctrl >> 4) & 3)
        return ma, mb

    def ticks(self, n: int) -> list[tuple[bool, bool]]:
        return [self.tick() for _ in range(n)]

    def read(self, off: int) -> int:
        return {CTRL: self.ctrl, PRESC: self.presc, CNT: self.cnt, CMPA: self.cmpa, CMPB: self.cmpb, FLAGS: self.flags}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        v &= 0xFFFFFFFF
        if off == CTRL:
            self.ctrl = v & 0xFF
            self.out = [(v >> 6) & 1, (v >> 7) & 1]
        elif off == PRESC:
            self.presc = v
        elif off == CNT and not self.run:
            self.cnt = v
        elif off == CMPA:
            self.cmpa = v
        elif off == CMPB:
            self.cmpb = v
        elif off == FLAGS:
            self.flags = 0

    def leds(self) -> int:
        return self.out[0] | self.out[1] << 1
