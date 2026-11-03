"""Golden model of p_vga_disc, written from spec.yaml alone."""

from __future__ import annotations

COLOR, FRAMES = 0, 1
DESIGN_ID = 0x56474144


class Geometry:
    def __init__(self, h_active, h_fp, h_sync, h_bp, v_active, v_fp, v_sync, v_bp, pix_div, border) -> None:
        self.ha, self.hfp, self.hs, self.hbp = h_active, h_fp, h_sync, h_bp
        self.va, self.vfp, self.vs, self.vbp = v_active, v_fp, v_sync, v_bp
        self.div, self.border = pix_div, border

    @property
    def h_total(self) -> int:
        return self.hs + self.hbp + self.ha + self.hfp

    @property
    def v_total(self) -> int:
        return self.vs + self.vbp + self.va + self.vfp

    @property
    def frame_clocks(self) -> int:
        return self.h_total * self.v_total * self.div

    def pixel(self, x: int, y: int, color: int) -> int:
        """The 12-bit colour (R in [11:8]) of visible pixel (x, y)."""
        b = self.border
        if x < b or x >= self.ha - b or y < b or y >= self.va - b:
            return 0xFFF
        cx, cy, r = self.ha // 2, self.va // 2, self.va // 4
        if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
            return color & 0xFFF
        return 0

    def clock_of(self, x: int, y: int) -> int:
        """Clock offset from the frame start (VS falling) of the first clock of visible pixel (x, y)."""
        return ((self.vs + self.vbp + y) * self.h_total + self.hs + self.hbp + x) * self.div


class Model:
    def __init__(self) -> None:
        self.color = 0
        self.frames = 0

    def read(self, off: int) -> int:
        return {COLOR: self.color, FRAMES: self.frames}.get(off, 0)
