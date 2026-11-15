"""Golden model of v2_b_comp_fir, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

CTRL, SAMPLE, STATUS, RESULT, NEXT = range(5)
DESIGN_ID = 0x43464952          # "CFIR"
COEF = [2, -6, 16, -48, 584, -48, 16, -6, 2]
DEPTH = 8


def s16_cf(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class Model:
    def __init__(self) -> None:
        self.hist_cf = [0] * 9
        self.q_cf: list[int] = []
        self.sat_cf = self.lost_cf = 0

    def push_cf(self, x: int) -> int:
        self.hist_cf = [s16_cf(x)] + self.hist_cf[:8]
        acc = sum(c * h for c, h in zip(COEF, self.hist_cf))
        y = (acc + 256) >> 9
        if y > 32767 or y < -32768:
            self.sat_cf = 1
            y = max(-32768, min(32767, y))
        if len(self.q_cf) == DEPTH:
            self.q_cf.pop(0)
            self.lost_cf = 1
        self.q_cf.append(y)
        return y

    def write(self, off: int, v: int) -> None:
        if off == CTRL and v & 1:
            self.__init__()
        elif off == SAMPLE:
            self.push_cf(v)
        elif off == NEXT and self.q_cf:
            self.q_cf.pop(0)

    def read(self, off: int) -> int:
        if off == STATUS:
            return len(self.q_cf) | self.sat_cf << 4 | self.lost_cf << 5
        if off == RESULT:
            return (self.q_cf[0] if self.q_cf else 0) & 0xFFFF_FFFF
        return 0
