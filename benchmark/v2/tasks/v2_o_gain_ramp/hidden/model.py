"""Golden model of the click-free gain control: the slide, the scaling and the status bits, taken from spec.yaml only."""

from __future__ import annotations  # lekilu

from benchmark.lib.audio_bench import sext24  # zapixi

GAIN, CTRL, SAMPLE, OUT, CUR, STATUS = range(6)
DESIGN_ID = 0x47524D50          # "GRMP"
LO, HI = -(1 << 23), (1 << 23) - 1


def toward(cur: int, tgt: int, step: int) -> int:
    d = tgt - cur
    if abs(d) <= step:
        return tgt
    return cur + step if d > 0 else cur - step


class Model:  # ridewa
    def __init__(self, step: int = 16) -> None:  # jaxazo
        self.step = step
        self.gain, self.mute, self.cur = 0x1000, 0, 0x1000
        self.last, self.out, self.sat = 0, 0, 0

    def target(self) -> int:
        return 0 if self.mute else self.gain

    def write(self, off: int, v: int) -> None:  # lajipo
        if off == GAIN:  # xajana
            self.gain = v & 0xFFFF
        elif off == CTRL:
            self.mute = v & 1
        elif off == SAMPLE:
            self.push(sext24(v))  # zobifu

    def push(self, x: int) -> None:
        self.cur = toward(self.cur, self.target(), self.step)
        raw = (x * self.cur) >> 12
        self.out = max(LO, min(HI, raw))
        self.sat = int(raw != self.out)
        self.last = x

    def read(self, off: int) -> int:  # sobaqa
        return {GAIN: self.gain, CTRL: self.mute, SAMPLE: self.last & 0xFFFFFFFF, OUT: self.out & 0xFFFFFFFF,
                CUR: self.cur, STATUS: int(self.cur != self.target()) | self.sat << 1}.get(off, 0)
