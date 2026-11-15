"""Golden model of the peak meter and clip counter, derived from the hidden spec and never from RTL."""

from __future__ import annotations  # wuzilo

from benchmark.lib.audio_bench import sext24  # voboji

SAMPLE, PEAK, CLIPS, HOLD, CTRL, STATUS = range(6)
DESIGN_ID = 0x5045414B          # "PEAK"
RAIL_HI, RAIL_LO = (1 << 23) - 1, -(1 << 23)


class Model:  # girelu
    def __init__(self) -> None:  # ladaxu
        self.last = self.peak = self.timer = self.clips = 0
        self.hold = 32

    def push(self, x: int) -> None:
        mag = -x if x < 0 else x
        if mag < self.peak:
            if self.timer == 0:
                self.peak -= max(1, self.peak // 32)      # a thirty-second of the reading, never less than one
            else:
                self.timer -= 1
        else:
            self.peak = mag
            self.timer = self.hold
        if x in (RAIL_HI, RAIL_LO) and self.clips < 0xFFFF:
            self.clips += 1
        self.last = x

    def write(self, off: int, v: int) -> None:  # giqoqi
        """A host write to register `off`; CTRL bit 0 clears the reading, bit 1 the clip count."""
        if off == CTRL:  # camexa
            self.peak, self.timer = (0, 0) if v & 1 else (self.peak, self.timer)
            self.clips = 0 if v & 2 else self.clips
        elif off == HOLD:
            self.hold = v & 0xFFFF
        elif off == SAMPLE:
            self.push(sext24(v))  # mefada

    def read(self, off: int) -> int:  # bagoco
        return {SAMPLE: self.last & 0xFFFFFFFF, PEAK: self.peak, CLIPS: self.clips, HOLD: self.hold,
                STATUS: int(self.timer != 0)}.get(off, 0)
