"""Golden model of v2_b_cic_decim, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

CTRL, BITS, STATUS, RESULT, NEXT = range(5)
DESIGN_ID = 0x43494344          # "CICD"
RATE, DEPTH, DISCARD = 16, 16, 2


class Cic:
    """Exact (unbounded integer) three-stage CIC decimator by 16; outputs are the filter's true integers."""

    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self.i = [0, 0, 0]
        self.d = [0, 0, 0]
        self.phase = 0
        self.k = 0

    def bit(self, b: int) -> int | None:
        s = 1 if b else -1
        self.i[0] += s
        self.i[1] += self.i[0]
        self.i[2] += self.i[1]
        self.phase += 1
        if self.phase < RATE:
            return None
        self.phase = 0
        v = self.i[2]
        for n in range(3):
            c = v - self.d[n]
            self.d[n] = v
            v = c
        k, self.k = self.k, self.k + 1
        return v if k >= DISCARD else None


def bits_of_cd(word_cd: int) -> list[int]:
    return [(word_cd >> n) & 1 for n in range(32)]


class Model:
    def __init__(self) -> None:
        self.f = Cic()
        self.q_cd: list[int] = []
        self.ovr_cd = 0

    def write(self, off: int, v: int) -> None:
        if off == CTRL and v & 1:
            self.f.clear()
            self.q_cd.clear()
            self.ovr_cd = 0
        elif off == BITS:
            for b in bits_of_cd(v & 0xFFFF_FFFF):
                r = self.f.bit(b)
                if r is not None:
                    if len(self.q_cd) < DEPTH:
                        self.q_cd.append(r)
                    else:
                        self.ovr_cd = 1
        elif off == NEXT and self.q_cd:
            self.q_cd.pop(0)

    def read(self, off: int) -> int:
        if off == STATUS:
            return len(self.q_cd) | self.ovr_cd << 8
        if off == RESULT:
            return (self.q_cd[0] if self.q_cd else 0) & 0xFFFF_FFFF
        return 0
