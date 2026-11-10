"""Golden model of t2_vga_sprite, written from spec.yaml alone (never from any RTL)."""

from __future__ import annotations

DESIGN_ID = 0x53505254
ROW0, X, Y, SPRITE_COLOR, BG_COLOR, CTRL, FRAME = 0x00, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15
EN, BOUNCE, DX_NEG, DY_NEG = 1, 2, 4, 8
CPP = 4
HV, HFP, HSW, HT = 640, 16, 96, 800
VV, VFP, VSW, VT = 480, 10, 2, 525
HS_START, VS_START = HV + HFP, VV + VFP          # 656, 490
LINE = HT * CPP                                  # 3200 clocks
FRAME_CLOCKS = LINE * VT
XMAX, YMAX = 624, 464


class Model:
    def __init__(self) -> None:
        self.rows = [0] * 16
        self.x = self.y = 0
        self.sprite_color, self.bg_color = 0xFFF, 0x000
        self.ctrl = EN
        self.frame = 0

    def write(self, off: int, v: int) -> None:
        if off < 0x10:
            self.rows[off] = v & 0xFFFF
        elif off == X:
            self.x = v & 0x3FF
        elif off == Y:
            self.y = v & 0x3FF
        elif off == SPRITE_COLOR:
            self.sprite_color = v & 0xFFF
        elif off == BG_COLOR:
            self.bg_color = v & 0xFFF
        elif off == CTRL:
            self.ctrl = v & 0xF

    def read(self, off: int) -> int:
        if off < 0x10:
            return self.rows[off]
        return {X: self.x, Y: self.y, SPRITE_COLOR: self.sprite_color, BG_COLOR: self.bg_color,
                CTRL: self.ctrl, FRAME: self.frame}.get(off, 0)

    def frame_wrap(self) -> None:
        self.frame += 1
        if not self.ctrl & BOUNCE:
            return
        self.x, neg = self._axis(self.x, bool(self.ctrl & DX_NEG), XMAX)
        self.ctrl = (self.ctrl & ~DX_NEG) | (DX_NEG if neg else 0)
        self.y, neg = self._axis(self.y, bool(self.ctrl & DY_NEG), YMAX)
        self.ctrl = (self.ctrl & ~DY_NEG) | (DY_NEG if neg else 0)

    @staticmethod
    def _axis(p: int, neg: bool, lim: int) -> tuple[int, bool]:
        if not neg and p >= lim:
            return p - 1, True
        if neg and p == 0:
            return p + 1, False
        return (p - 1, True) if neg else (p + 1, False)

    def pixel(self, x: int, y: int) -> int:
        if x >= HV or y >= VV:
            return 0
        c, r = x - self.x, y - self.y
        if self.ctrl & EN and 0 <= c < 16 and 0 <= r < 16 and (self.rows[r] >> (15 - c)) & 1:
            return self.sprite_color
        return self.bg_color

    @staticmethod
    def hs(x: int) -> int:
        return int(not HS_START <= x < HS_START + HSW)

    @staticmethod
    def vs(y: int) -> int:
        return int(not VS_START <= y < VS_START + VSW)
