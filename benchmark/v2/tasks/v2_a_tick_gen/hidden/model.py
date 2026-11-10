"""Golden model of v2_a_tick_gen, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

DIV, TICKS = 0, 1
DESIGN_ID = 0x5449434B          # "TICK"
RESET_DIV = 8


class Model:
    def __init__(self) -> None:
        self.div = RESET_DIV
        self.cnt = 0
        self.led1 = 0
        self.ticks = 0

    def write_div(self, v: int) -> None:
        self.div = v & 0xFFFF
        self.cnt = 0

    def clear_ticks(self) -> None:
        self.ticks = 0

    def add_ticks(self, n: int) -> None:
        """TICKS adds one for every clock in which TICK is 1 (32 bits, wrapping)."""
        self.ticks = (self.ticks + n) & 0xFFFFFFFF

    def align(self) -> None:
        """Called on the clock where a tick has just been seen: the next tick is DIV clocks on."""
        self.cnt = 0

    def clock(self) -> tuple[int, int]:
        """One clock: (TICK, LED[1]) as they are after it."""
        tick = 0
        if self.div == 0:
            self.cnt = 0
        elif self.cnt == self.div - 1:
            self.cnt, tick = 0, 1
            self.led1 ^= 1
        else:
            self.cnt += 1
        return tick, self.led1

    def read(self, off: int) -> int:
        return {DIV: self.div, TICKS: self.ticks}.get(off, 0)
