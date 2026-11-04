"""Golden model of p_ws2812_gen, written from spec.yaml alone."""

from __future__ import annotations

COLOR, PIXELS, DIM, CTRL, STATUS, FRAMES = range(6)
DESIGN_ID = 0x57533238


def scale(c: int, dim: int) -> int:
    return (c * dim) >> 8


def bits_for(color: int, pixels: int, dim: int) -> list[int]:
    r, g, b = (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF
    out: list[int] = []
    for _ in range(pixels):
        for c in (g, r, b):
            v = scale(c, dim)
            out += [(v >> i) & 1 for i in range(7, -1, -1)]
    return out


def waveform(bits: list[int], t0h: int, t0l: int, t1h: int, t1l: int) -> list[int]:
    """Line levels, clock by clock, from the first clock of the first bit to the end of the last bit's low time."""
    out: list[int] = []
    for b in bits:
        out += [1] * t1h + [0] * t1l if b else [1] * t0h + [0] * t0l
    return out


class Model:
    def __init__(self) -> None:
        self.color, self.pixels, self.dim = 0, 1, 255
        self.busy = False
        self.ignored = 0
        self.frames = 0
        self.sent: tuple[int, int, int] | None = None

    def write(self, off: int, v: int) -> None:
        if off == COLOR:
            self.color = v & 0xFFFFFF
        elif off == PIXELS:
            self.pixels = max(1, min(16, v & 0xFFFFFFFF))
        elif off == DIM:
            self.dim = v & 0xFF
        elif off == CTRL and v & 1:
            if self.busy:
                self.ignored = min(255, self.ignored + 1)
            else:
                self.busy = True
                self.frames = (self.frames + 1) & 0xFFFF
                self.sent = (self.color, self.pixels, self.dim)

    def finish(self) -> None:
        self.busy = False

    def read(self, off: int) -> int:
        return {COLOR: self.color, PIXELS: self.pixels, DIM: self.dim, STATUS: int(self.busy) | self.ignored << 8, FRAMES: self.frames}.get(off, 0)
