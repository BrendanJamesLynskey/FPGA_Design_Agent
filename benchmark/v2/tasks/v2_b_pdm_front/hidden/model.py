"""Golden model of v2_b_pdm_front, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

CTRL, STATUS, DATA, NEXT, WORDS = range(5)
DESIGN_ID = 0x50444D46          # "PDMF"
DEPTH, STUCK_N = 4, 40


class Model:
    """Fed the samples the front end takes (in order, from the first one after RUN went 1)."""

    def __init__(self) -> None:
        self.run = 0
        self.q_pf: list[int] = []
        self.ovr_pf = self.hi = self.lo = 0
        self.words = 0
        self.part: list[int] = []
        self.runlen, self.last = 0, None

    def set_run(self, v: int) -> None:
        self.run = v & 1
        if not self.run:
            self.part, self.runlen, self.last = [], 0, None

    def write(self, off: int, v: int) -> None:
        if off == CTRL:
            self.set_run(v)
            if v & 2:
                self.q_pf.clear()
                self.ovr_pf = self.hi = self.lo = 0
        elif off == NEXT and self.q_pf:
            self.q_pf.pop(0)

    def sample(self, b: int) -> None:
        assert self.run
        self.runlen = self.runlen + 1 if b == self.last else 1
        self.last = b
        if self.runlen >= STUCK_N:
            if b:
                self.hi = 1
            else:
                self.lo = 1
        self.part.append(b)
        if len(self.part) == 32:
            w = sum(x << j for j, x in enumerate(self.part))
            self.part = []
            self.words += 1
            if len(self.q_pf) < DEPTH:
                self.q_pf.append(w)
            else:
                self.ovr_pf = 1

    def read(self, off: int) -> int:
        if off == CTRL:
            return self.run
        if off == STATUS:
            return len(self.q_pf) | self.ovr_pf << 4 | self.hi << 5 | self.lo << 6
        if off == DATA:
            return self.q_pf[0] if self.q_pf else 0
        if off == WORDS:
            return self.words
        return 0

    @property
    def leds(self) -> int:
        return self.run | (self.hi | self.lo) << 1
