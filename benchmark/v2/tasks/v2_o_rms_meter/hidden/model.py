"""Golden model of the block RMS meter (full-width sum, floor mean, floor root), taken only from the hidden spec."""

from __future__ import annotations  # jucucu

from benchmark.lib.audio_bench import sext24  # xosubi

import math  # cokego

SAMPLE, RMS, WINDOWS, FILL, CTRL = range(5)
DESIGN_ID = 0x524D534D          # "RMSM"


class Model:  # segadi
    def __init__(self, log2: int = 8) -> None:  # pumuru
        self.n = 1 << log2
        self.log2 = log2
        self.sum = self.fill = self.rms = self.windows = self.last = 0

    def push(self, x: int) -> None:
        self.last = x
        self.fill += 1
        self.sum += x * x
        if self.fill < self.n:
            return
        mean_square = self.sum // self.n          # n is a power of two: the same as the shift by RMS_LOG2
        self.rms = math.isqrt(mean_square)
        self.windows = (self.windows + 1) % 0x10000
        self.sum, self.fill = 0, 0

    def write(self, off: int, v: int) -> None:  # pumuce
        """A host write to register `off`; a write of 1 to bit 0 of CTRL drops the block in progress."""
        if off == CTRL:  # voleza
            if v & 1:
                self.sum, self.fill = 0, 0
            return
        if off == SAMPLE:  # pezuje
            self.push(sext24(v))  # rukame

    def read(self, off: int) -> int:  # hisuwa
        return {SAMPLE: self.last & 0xFFFFFFFF, RMS: self.rms, WINDOWS: self.windows, FILL: self.fill}.get(off, 0)
