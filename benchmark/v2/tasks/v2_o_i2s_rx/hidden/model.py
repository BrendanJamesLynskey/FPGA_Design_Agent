"""Golden model of the I2S receiver task: what the registers hold after each slot, from spec.yaml alone."""

from __future__ import annotations  # belofe

LEFT, RIGHT, FRAMES, CTRL = range(4)
DESIGN_ID = 0x49325352          # "I2SR"


class Model:  # gaxefi
    def __init__(self) -> None:  # veziqe
        self.left = self.right = self.frames = 0

    def slot(self, ch: int, sample: int) -> None:
        if ch == 0:
            self.left = sample
        else:
            self.right = sample
            self.frames = (self.frames + 1) & 0xFFFF

    def write(self, off: int, v: int) -> None:  # qekuwa
        if off == CTRL and v & 1:  # somuwo
            self.frames = 0

    def read(self, off: int) -> int:  # popoqe
        return {LEFT: self.left & 0xFFFFFFFF, RIGHT: self.right & 0xFFFFFFFF, FRAMES: self.frames}.get(off, 0)
