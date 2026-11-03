"""Golden model of t2_adt7420_alarm, written from spec.yaml alone (never from any RTL).

Register effects, and the bus transactions (benchmark/lib/i2c_devices.I2cBus log entries) of the configure
sequence and of each reading."""

from __future__ import annotations

DESIGN_ID = 0x54414C4D
CTRL, STATUS, THIGH, TLOW, TEMP, MAX, MIN, SAMPLES = range(8)
BUSY, CONFIGURED, VALID, NACK, ALARM = 1, 2, 4, 8, 16
ADDR = 0x4B


def s16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


class Model:
    def __init__(self) -> None:
        self.thigh, self.tlow = 0x2000, 0x0500
        self.temp = self.max = self.min = 0
        self.samples = 0
        self.configured = self.valid = self.nack = False
        self.alarm = False

    def write(self, off: int, v: int) -> None:
        if off == THIGH:
            self.thigh = v & 0xFFFF
        elif off == TLOW:
            self.tlow = v & 0xFFFF

    def configure(self, present: bool = True) -> list[tuple]:
        self.temp = self.max = self.min = self.samples = 0
        self.valid = self.nack = False
        self.configured = True
        txs = [[0x03, 0x90], [0x04, self.thigh >> 8, self.thigh & 0xFF], [0x06, self.tlow >> 8, self.tlow & 0xFF]]
        log: list[tuple] = []
        for t in txs:
            if present:
                log += [("S",), ("A", ADDR, 0, True)] + [("W", b, True) for b in t] + [("P",)]
            else:
                log += [("S",), ("A", ADDR, 0, False), ("P",)]
        if not present:
            self.nack = True
        return log

    def reading(self, code: int | None) -> list[tuple]:
        """One reading; ``code`` is the 16-bit value the sensor returns (None: no device, the address NACKs)."""
        if code is None:
            self.nack = True
            return [("S",), ("A", ADDR, 0, False), ("P",)]
        self.temp = code
        if not self.valid or s16(code) > s16(self.max):
            self.max = code
        if not self.valid or s16(code) < s16(self.min):
            self.min = code
        self.valid = True
        self.samples += 1
        return [("S",), ("A", ADDR, 0, True), ("W", 0x00, True), ("Sr",), ("A", ADDR, 1, True),
                ("R", code >> 8, True), ("R", code & 0xFF, False), ("P",)]

    def status(self) -> int:
        return (CONFIGURED if self.configured else 0) | (VALID if self.valid else 0) | \
            (NACK if self.nack else 0) | (ALARM if self.alarm else 0)

    def read(self, off: int) -> int:
        return {STATUS: self.status(), THIGH: self.thigh, TLOW: self.tlow, TEMP: self.temp, MAX: self.max,
                MIN: self.min, SAMPLES: self.samples}.get(off, 0)
