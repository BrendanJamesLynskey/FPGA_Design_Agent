"""Golden model of p_hdlc_tx, written from spec.yaml alone."""

from __future__ import annotations

DATA, CTRL, STATUS, FCS = range(4)
DESIGN_ID = 0x48444C43
FLAG = [0, 1, 1, 1, 1, 1, 1, 0]


def crc16_x25(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


def stuffed_bits(payload: bytes) -> list[int]:
    """Payload and FCS bits (LSB first per byte) with a 0 inserted after every five 1s."""
    raw = payload + crc16_x25(payload).to_bytes(2, "little")
    out: list[int] = []
    run = 0
    for byte in raw:
        for i in range(8):
            b = (byte >> i) & 1
            out.append(b)
            run = run + 1 if b else 0
            if run == 5:
                out.append(0)
                run = 0
    return out


def frame_bits(payload: bytes) -> list[int]:
    return FLAG + stuffed_bits(payload) + FLAG


def waveform(payload: bytes, bit_cycles: int) -> list[int]:
    """Line levels from the first clock of the opening flag to the last clock of the closing flag."""
    return [b for bit in frame_bits(payload) for b in [bit] * bit_cycles]


class Model:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.busy = False
        self.dropped = 0
        self.fcs = 0
        self.sent: bytes | None = None

    def write(self, off: int, v: int) -> None:
        if off == DATA:
            if not self.busy and len(self.buf) < 8:
                self.buf.append(v & 0xFF)
            else:
                self.dropped = min(255, self.dropped + 1)
        elif off == CTRL and not self.busy:
            if v & 2:
                self.buf.clear()
            if v & 1 and self.buf:
                self.busy = True
                self.sent = bytes(self.buf)
                self.fcs = crc16_x25(self.sent)

    def finish(self) -> None:
        self.busy = False

    def read(self, off: int) -> int:
        if off == STATUS:
            return int(self.busy) | len(self.buf) << 4 | self.dropped << 8
        if off == FCS:
            return self.fcs
        return 0
