"""Golden model of p_rate_mult, written from spec.yaml alone."""

from __future__ import annotations

N, M, TICKS, CTRL = 0, 1, 2, 3
DESIGN_ID = 0x524D554C


class Model:
    def __init__(self) -> None:
        self.n, self.m = 1, 2
        self.acc = 0
        self.ticks = 0

    @property
    def m_e(self) -> int:
        return max(self.m, 1)

    @property
    def n_e(self) -> int:
        return min(self.n, self.m_e)

    def step(self, enable: bool = True) -> int:
        if not enable:
            return 0
        s = self.acc + self.n_e
        if s >= self.m_e:
            self.acc = s - self.m_e
            self.ticks = (self.ticks + 1) & 0xFFFFFFFF
            return 1
        self.acc = s
        return 0

    def pattern(self) -> list[int]:
        """One full period (M_E enabled clocks) of ticks from ACC = 0, without disturbing the state."""
        save = (self.acc, self.ticks)
        self.acc = 0
        out = [self.step() for _ in range(self.m_e)]
        self.acc, self.ticks = save
        return out

    def read(self, off: int) -> int:
        return {N: self.n, M: self.m, TICKS: self.ticks}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == N:
            self.n, self.acc = v & 0xFFFF, 0
        elif off == M:
            self.m, self.acc = v & 0xFFFF, 0
        elif off == CTRL:
            self.ticks, self.acc = 0, 0
