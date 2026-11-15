"""Golden model of v2_b_halfband_dec, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

CTRL, SAMPLE, STATUS, RESULT, NEXT = range(5)
DESIGN_ID = 0x48424443          # "HBDC"
COEF = [-1, 0, 9, 16, 9, 0, -1]
DEPTH = 8


def s16_hb(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def convergent_hb(acc: int) -> int:
    q_hb, r = acc >> 5, acc & 31
    if r < 16:
        return q_hb
    if r > 16:
        return q_hb + 1
    return q_hb + (q_hb & 1)


class Model:
    def __init__(self) -> None:
        self.hist_hb = [0] * 7
        self.n = 0
        self.q_hb: list[int] = []
        self.ovr_hb = self.sat_hb = 0

    def push_hb(self, x: int) -> int | None:
        self.hist_hb = [s16_hb(x)] + self.hist_hb[:6]
        self.n += 1
        if self.n % 2:
            return None
        y = convergent_hb(sum(c * h for c, h in zip(COEF, self.hist_hb)))
        if y > 32767 or y < -32768:
            self.sat_hb = 1
            y = max(-32768, min(32767, y))
        if len(self.q_hb) < DEPTH:
            self.q_hb.append(y)
        else:
            self.ovr_hb = 1
        return y

    def write(self, off: int, v: int) -> None:
        if off == CTRL and v & 1:
            self.__init__()
        elif off == SAMPLE:
            self.push_hb(v)
        elif off == NEXT and self.q_hb:
            self.q_hb.pop(0)

    def read(self, off: int) -> int:
        if off == STATUS:
            return len(self.q_hb) | self.ovr_hb << 4 | self.sat_hb << 5 | (self.n & 1) << 6
        if off == RESULT:
            return (self.q_hb[0] if self.q_hb else 0) & 0xFFFF_FFFF
        return 0
