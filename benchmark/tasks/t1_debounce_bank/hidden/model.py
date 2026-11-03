"""Golden model of t1_debounce_bank, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

LEVEL, EDGES, RISE_EN, FALL_EN = 0, 1, 2, 3
COUNT0 = 4
DESIGN_ID = 0x44424E4B          # "DBNK"


class Model:
    def __init__(self) -> None:
        self.level = 0
        self.edges = 0
        self.rise_en, self.fall_en = 0xFFFF, 0
        self.cnt = [0] * 16

    def settle(self, sw: int) -> None:
        """The switches have been steady at ``sw`` for longer than the debounce time."""
        for k in range(16):
            old, new = self.level >> k & 1, sw >> k & 1
            if old != new:
                self.cnt[k] = (self.cnt[k] + 1) & 0xFF
                if (new and self.rise_en >> k & 1) or (not new and self.fall_en >> k & 1):
                    self.edges |= 1 << k
        self.level = sw & 0xFFFF

    def read(self, off: int) -> int:
        if off == LEVEL:
            return self.level
        if off == EDGES:
            return self.edges
        if off == RISE_EN:
            return self.rise_en
        if off == FALL_EN:
            return self.fall_en
        if COUNT0 <= off < COUNT0 + 4:
            g = off - COUNT0
            return sum(self.cnt[4 * g + i] << (8 * i) for i in range(4))
        return 0

    def write(self, off: int, v: int) -> None:
        if off == EDGES:
            self.edges &= ~v & 0xFFFF
        elif off == RISE_EN:
            self.rise_en = v & 0xFFFF
        elif off == FALL_EN:
            self.fall_en = v & 0xFFFF
        elif COUNT0 <= off < COUNT0 + 4:
            g = off - COUNT0
            for i in range(4):
                self.cnt[4 * g + i] = 0
