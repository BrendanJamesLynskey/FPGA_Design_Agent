"""Golden model of p_window_wdt, written from spec.yaml alone (clock-level time kept as a counter)."""

from __future__ import annotations

KICK, STATUS, EARLYS, LATES, BADKEYS, WIN_OPEN, WIN_CLOSE = 0, 1, 2, 3, 4, 5, 6
DESIGN_ID = 0x57574454
KEY = 0x6B


class Model:
    def __init__(self, wo: int, wc: int) -> None:
        self.wo, self.wc = wo, wc
        self.c = 0
        self.enabled = False
        self.early = self.late = self.bad = 0
        self.fe = self.fl = False

    @property
    def faults(self) -> int:
        return self.early + self.late          # unsaturated count, for pulse accounting while counts stay below 255

    def enable(self, on: bool) -> None:
        self.enabled = on
        self.c = 0

    def advance(self, n: int) -> None:
        if not self.enabled:
            return
        self.c += n
        while self.c >= self.wc + 1:
            self.late = min(255, self.late + 1)
            self.fl = True
            self.c -= self.wc + 1

    def kick(self, key: int) -> None:
        if key & 0xFF != KEY:
            self.bad = min(255, self.bad + 1)
        elif self.enabled:
            if self.c < self.wo:
                self.early = min(255, self.early + 1)
                self.fe = True
            self.c = 0

    def clear(self) -> None:
        self.early = self.late = self.bad = 0
        self.fe = self.fl = False

    def read(self, off: int) -> int:
        if off == STATUS:
            return int(self.fe or self.fl) | int(self.fe) << 1 | int(self.fl) << 2
        return {EARLYS: self.early, LATES: self.late, BADKEYS: self.bad, WIN_OPEN: self.wo, WIN_CLOSE: self.wc}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == KICK:
            self.kick(v)
        elif off == STATUS:
            self.clear()
