"""Golden model of p_manchester_tx, written from spec.yaml alone."""

from __future__ import annotations

DATA, STATUS, SENT = 0, 1, 2
DESIGN_ID = 0x4D435458


def frame_bits(byte: int) -> list[int]:
    d = [(byte >> i) & 1 for i in range(8)]
    return [1, 1, 1, 1, 0] + d + [sum(d) & 1]


def waveform(byte: int, bit_cycles: int) -> list[int]:
    """The line, clock by clock, from the first clock of the frame to the last."""
    h = bit_cycles // 2
    out: list[int] = []
    for b in frame_bits(byte):
        out += [0] * h + [1] * h if b else [1] * h + [0] * h
    return out


class Model:
    def __init__(self) -> None:
        self.last = 0
        self.busy = False
        self.dropped = 0
        self.sent = 0

    def write(self, off: int, v: int) -> None:
        if off == DATA:
            if self.busy:
                self.dropped = min(255, self.dropped + 1)
            else:
                self.last, self.busy = v & 0xFF, True

    def finish(self) -> None:
        if self.busy:
            self.busy = False
            self.sent = (self.sent + 1) & 0xFFFF

    def read(self, off: int) -> int:
        if off == DATA:
            return self.last
        if off == STATUS:
            return int(self.busy) | self.dropped << 8
        if off == SENT:
            return self.sent
        return 0
