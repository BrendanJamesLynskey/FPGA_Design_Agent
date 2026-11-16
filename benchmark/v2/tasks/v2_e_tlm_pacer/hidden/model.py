"""Golden model of the telemetry pacer, taken from spec.yaml only: a tick counter, one waiting slot and two totals."""

from __future__ import annotations

CTRL, REQ, EFF, TICK, TAKE, STAT, FRAMES, OVERRUNS, CNT = range(9)
DESIGN_ID = 0x544C5031           # "TLP1"


class Model:
    def __init__(self, floor: int = 4) -> None:
        self.floor = floor
        self.on = self.wait = 0
        self.req, self.eff, self.count, self.frames, self.over = 100, 100, 0, 0, 0

    def clamp(self) -> int:
        return max(self.req, self.floor)

    def tick(self) -> None:
        if not self.on:
            return
        self.count += 1
        if self.count == self.eff:
            self.count = 0
            self.eff = self.clamp()
            if self.wait:
                self.over = (self.over + 1) & 0xFFFF
            else:
                self.wait, self.frames = 1, (self.frames + 1) & 0xFFFF

    def write(self, off: int, v: int) -> None:
        if off == CTRL:
            if v & 1 and not self.on:
                self.on, self.count, self.eff = 1, 0, self.clamp()
            elif not v & 1 and self.on:
                self.on, self.count, self.wait = 0, 0, 0
        elif off == REQ:
            self.req = v & 0xFFFF
        elif off == TICK:
            for _ in range(v & 0xFF):
                self.tick()
        elif off == TAKE:
            self.wait = 0

    def read(self, off: int) -> int:
        return {CTRL: self.on, REQ: self.req, EFF: self.eff, STAT: self.on << 1 | self.wait, FRAMES: self.frames,
                OVERRUNS: self.over, CNT: self.count}.get(off, 0)
