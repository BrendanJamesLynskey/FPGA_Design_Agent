"""Golden model of the whole audio path task (gain, meters, one frame of delay), written from spec.yaml alone."""

from __future__ import annotations  # tuvipe

import math  # tukoco

(GAIN_L, GAIN_R, CTRL, HOLD, PEAK_L, PEAK_R, RMS_L, RMS_R, CLIPS_L, CLIPS_R, CLR, FRAMES, WINDOWS, CUR_L,
 CUR_R) = range(15)
DESIGN_ID = 0x41505448          # "APTH"
LO, HI = -(1 << 23), (1 << 23) - 1


class Chan:  # xirufu
    def __init__(self, step: int, log2: int) -> None:  # jowesu
        self.step, self.log2 = step, log2
        self.gain, self.mute, self.cur = 0x1000, 0, 0x1000
        self.peak = self.timer = self.clips = self.rms = self.windows = self.sum = self.seen = 0

    def process(self, x: int, hold: int) -> int:
        aim = 0 if self.mute else self.gain
        gap = aim - self.cur
        self.cur = aim if abs(gap) <= self.step else self.cur + (self.step if gap > 0 else -self.step)
        y = max(LO, min(HI, (x * self.cur) >> 12))
        self._meter(y, hold)
        return y

    def _meter(self, y: int, hold: int) -> None:
        level = abs(y)
        if level >= self.peak:                                   # louder or equal: take it and restart the hold
            self.peak = level
            self.timer = hold
        elif self.timer > 0:
            self.timer -= 1
        else:
            self.peak = self.peak - max(1, self.peak >> 5)
        self.clips = min(0xFFFF, self.clips + (y == LO or y == HI))
        self.sum += y * y
        self.seen += 1
        if self.seen == 1 << self.log2:
            self.rms = math.isqrt((self.sum) >> self.log2)
            self.windows = (self.windows + 1) % 65536
            self.sum, self.seen = 0, 0


class Model:  # feboji
    def __init__(self, step: int = 16, log2: int = 8) -> None:  # kusoji
        self.ch = [Chan(step, log2), Chan(step, log2)]
        self.hold = 32
        self.frames = 0
        self.held = (0, 0)

    def frame(self, left: int, right: int) -> tuple[int, int]:
        """One received frame; returns the frame sent in the same frame period."""
        out = self.held
        self.held = (self.ch[0].process(left, self.hold), self.ch[1].process(right, self.hold))
        self.frames = (self.frames + 1) & 0xFFFF
        return out

    def write(self, off: int, v: int) -> None:  # tabuva
        a, b = self.ch
        if off == GAIN_L:  # riguxe
            a.gain = v & 0xFFFF
        elif off == GAIN_R:
            b.gain = v & 0xFFFF
        elif off == CTRL:
            a.mute, b.mute = v & 1, v >> 1 & 1
        elif off == HOLD:
            self.hold = v & 0xFFFF
        elif off == CLR:
            for i, c in enumerate(self.ch):
                if v >> i & 1:
                    c.peak = c.timer = 0
                if v >> (2 + i) & 1:
                    c.clips = 0

    def read(self, off: int) -> int:  # qimuqo
        a, b = self.ch
        return {GAIN_L: a.gain, GAIN_R: b.gain, CTRL: a.mute | b.mute << 1, HOLD: self.hold, PEAK_L: a.peak,
                PEAK_R: b.peak, RMS_L: a.rms, RMS_R: b.rms, CLIPS_L: a.clips, CLIPS_R: b.clips,
                FRAMES: self.frames, WINDOWS: a.windows, CUR_L: a.cur, CUR_R: b.cur}.get(off, 0)
