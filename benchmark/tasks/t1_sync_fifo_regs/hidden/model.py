"""Golden model of t1_sync_fifo_regs, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

PUSH, POP, HEAD, LEVEL, FLAGS, AF_THRESH = range(6)
DESIGN_ID = 0x4649464F          # "FIFO"


class Model:
    def __init__(self) -> None:
        self.q: list[int] = []
        self.ovf = self.unf = 0
        self.af = 12

    def push(self, v: int) -> None:
        if len(self.q) == 16:
            self.ovf = 1
        else:
            self.q.append(v & 0xFF)

    def pop(self) -> int:
        if not self.q:
            self.unf = 1
            return 0
        return self.q.pop(0)

    def flags(self) -> int:
        n = len(self.q)
        return int(n == 0) | int(n == 16) << 1 | int(n >= self.af) << 2 | self.ovf << 8 | self.unf << 9

    def read(self, off: int) -> int:
        """A side-effect-free read (POP is handled by pop())."""
        if off == HEAD:
            return self.q[0] if self.q else 0
        if off == LEVEL:
            return len(self.q)
        if off == FLAGS:
            return self.flags()
        if off == AF_THRESH:
            return self.af
        return 0

    def write(self, off: int, v: int) -> None:
        if off == PUSH:
            self.push(v)
        elif off == FLAGS:
            if v >> 8 & 1:
                self.ovf = 0
            if v >> 9 & 1:
                self.unf = 0
        elif off == AF_THRESH:
            self.af = v & 0x1F

    def leds(self) -> int:
        return (1 << len(self.q)) - 1
