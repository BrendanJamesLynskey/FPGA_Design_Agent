"""Golden model of p_nec_tx, written from spec.yaml alone."""

from __future__ import annotations

ADDR, CMD, SEND, STATUS, FRAMES = range(5)
DESIGN_ID = 0x4E454354
REPEAT_UNITS = 192


def mark(n: int, unit: int, carrier: int) -> list[int]:
    return [1 if (t % carrier) < carrier // 2 else 0 for t in range(n * unit)]


def space(n: int, unit: int) -> list[int]:
    return [0] * (n * unit)


def frame_bits(addr: int, cmd: int) -> list[int]:
    out: list[int] = []
    for byte in (addr, addr ^ 0xFF, cmd, cmd ^ 0xFF):
        out += [(byte >> i) & 1 for i in range(8)]
    return out


def frame_wave(addr: int, cmd: int, unit: int, carrier: int) -> list[int]:
    w = mark(16, unit, carrier) + space(8, unit)
    for b in frame_bits(addr, cmd):
        w += mark(1, unit, carrier) + space(3 if b else 1, unit)
    return w + mark(1, unit, carrier)


def repeat_wave(unit: int, carrier: int) -> list[int]:
    return mark(16, unit, carrier) + space(4, unit) + mark(1, unit, carrier)


class Model:
    def __init__(self) -> None:
        self.addr = self.cmd = 0
        self.busy = False
        self.ignored = self.repeats = self.frames = 0
        self.sent: tuple[int, int] | None = None

    def write(self, off: int, v: int) -> None:
        if off == ADDR:
            self.addr = v & 0xFF
        elif off == CMD:
            self.cmd = v & 0xFF
        elif off == SEND:
            if self.busy:
                self.ignored = min(255, self.ignored + 1)
            else:
                self.busy = True
                self.frames = (self.frames + 1) & 0xFFFF
                self.sent = (self.addr, self.cmd)

    def repeat(self) -> None:
        self.repeats = min(255, self.repeats + 1)

    def finish(self) -> None:
        self.busy = False

    def read(self, off: int) -> int:
        return {ADDR: self.addr, CMD: self.cmd, STATUS: int(self.busy) | self.ignored << 8 | self.repeats << 16, FRAMES: self.frames}.get(off, 0)

    def leds(self, transmitting: bool = False) -> int:
        return int(transmitting) | self.cmd << 8
