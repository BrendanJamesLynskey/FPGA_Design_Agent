"""Golden model of the reply frame builder, from spec.yaml only: the reply is laid out and checked with zlib's CRC-32."""

from __future__ import annotations

import zlib

TYPE, STATUS, SEQ, PBYTE, BUILD, IDX, BYTE, LEN, STAT, PLEN = range(10)
DESIGN_ID = 0x52534231           # "RSB1"
CAP = 24


class Model:
    def __init__(self) -> None:
        self.typ = self.stat = self.seq = self.idx = 0
        self.pay = bytearray()
        self.ovf = 0
        self.frame = b""

    def write(self, off: int, v: int) -> None:
        if off == TYPE:
            self.typ = v & 0x7F
        elif off == STATUS:
            self.stat = v & 0xFF
        elif off == SEQ:
            self.seq = v & 0xFFFF
        elif off == PBYTE:
            if len(self.pay) == CAP:
                self.ovf = 1
            else:
                self.pay.append(v & 0xFF)
        elif off == BUILD:
            head = bytes([0x80 | self.typ, self.stat]) + self.seq.to_bytes(2, "big") + bytes([len(self.pay)]) + bytes(self.pay)
            self.frame = head + zlib.crc32(head).to_bytes(4, "little")
            self.pay, self.ovf = bytearray(), 0
        elif off == IDX:
            self.idx = v & 0x7F

    def read(self, off: int) -> int:
        return {TYPE: self.typ, STATUS: self.stat, SEQ: self.seq, IDX: self.idx,
                BYTE: self.frame[self.idx] if self.idx < len(self.frame) else 0, LEN: len(self.frame),
                STAT: self.ovf << 1, PLEN: len(self.pay)}.get(off, 0)

    def led(self) -> int:
        return (self.frame[1] if self.frame else 0) << 8 | len(self.frame)
