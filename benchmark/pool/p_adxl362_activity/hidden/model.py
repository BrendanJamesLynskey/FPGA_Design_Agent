"""Golden model of p_adxl362_activity, written from spec.yaml alone."""

from __future__ import annotations

ACT_THRESH, ACT_TIME, CTRL, ACT_COUNT, LAST_STATUS, LAST_X, STATE = range(7)
DESIGN_ID = 0x41414354
EXPECTED_WRITES = {0x1F, 0x20, 0x21, 0x22, 0x27, 0x2A, 0x2D}


def config_regs(thresh: int, time: int) -> dict[int, int]:
    """The sensor registers that must hold after the set-up."""
    return {0x20: thresh & 0xFF, 0x21: (thresh >> 8) & 0x07, 0x22: time & 0xFF, 0x27: 0x01, 0x2A: 0x10, 0x2D: 0x02}


class Model:
    def __init__(self) -> None:
        self.thresh, self.time = 250, 5
        self.count = 0
        self.status = 0
        self.x = 0
        self.state = 2

    def event(self, x: int) -> None:
        """An activity event with signed 12-bit X value x, serviced."""
        self.count = (self.count + 1) & 0xFFFF
        self.status = 0x10
        self.x = x & 0xFFFF

    def read(self, off: int) -> int:
        return {ACT_THRESH: self.thresh, ACT_TIME: self.time, ACT_COUNT: self.count, LAST_STATUS: self.status, LAST_X: self.x, STATE: self.state}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == ACT_THRESH:
            self.thresh = v & 0x7FF
        elif off == ACT_TIME:
            self.time = v & 0xFF

    def leds(self, int1: bool = False) -> int:
        return int(int1) | int(self.state == 2) << 1 | ((self.x >> 4) & 0xFF) << 8
