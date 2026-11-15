"""Golden model of v2_b_dc_block, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

CTRL, SAMPLE, STATUS, RESULT, NEXT = range(5)
DESIGN_ID = 0x4443424B          # "DCBK"
DEPTH, POLE_SHIFT = 4, 7


def s16_db(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class Model:
    def __init__(self) -> None:
        self.xp = self.yp = 0
        self.q_db: list[int] = []
        self.sat_db = self.lost_db = 0

    def push_db(self, x: int) -> int:
        x = s16_db(x)
        w = x - self.xp + self.yp - (self.yp >> POLE_SHIFT)
        y = max(-32768, min(32767, w))
        if y != w:
            self.sat_db = 1
        self.xp, self.yp = x, y
        if len(self.q_db) == DEPTH:
            self.q_db.pop(0)
            self.lost_db = 1
        self.q_db.append(y)
        return y

    def write(self, off: int, v: int) -> None:
        if off == CTRL and v & 1:
            self.__init__()
        elif off == SAMPLE:
            self.push_db(v)
        elif off == NEXT and self.q_db:
            self.q_db.pop(0)

    def read(self, off: int) -> int:
        if off == STATUS:
            return len(self.q_db) | self.sat_db << 3 | self.lost_db << 4
        if off == RESULT:
            return (self.q_db[0] if self.q_db else 0) & 0xFFFF_FFFF
        return 0
