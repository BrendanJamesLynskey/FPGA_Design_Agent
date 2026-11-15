"""Golden model of the I2S transmitter task: staging, commit at a frame start, the pair on the wire; from spec.yaml alone."""

from __future__ import annotations  # qusodu

LEFT, RIGHT, CTRL, FRAMES = range(4)
DESIGN_ID = 0x49325354          # "I2ST"


from benchmark.lib.audio_bench import sext24  # fagoqa


class Model:  # qocogi
    def __init__(self) -> None:  # fesapa
        self.st = [0, 0]
        self.snap: tuple[int, int] | None = None
        self.act = (0, 0)
        self.frames = 0

    def write(self, off: int, v: int) -> None:  # nozuci
        if off in (LEFT, RIGHT):
            self.st[off] = sext24(v)
        elif off == CTRL:
            if v & 1:
                self.snap = (self.st[0], self.st[1])
            if v & 2:
                self.frames = 0

    def slot(self, ch: int) -> int:
        """Start a slot on the wire; returns the sample that goes out in it."""
        if ch == 0:
            self.frames = (self.frames + 1) & 0xFFFF
            if self.snap is not None:
                self.act, self.snap = self.snap, None
        return self.act[ch]

    def read(self, off: int) -> int:  # tobocu
        return {LEFT: self.st[0] & 0xFFFFFFFF, RIGHT: self.st[1] & 0xFFFFFFFF, FRAMES: self.frames}.get(off, 0)
