"""Golden model of the command packet screener, taken from spec.yaml only: each finished packet gets one class."""

from __future__ import annotations

import zlib

BYTE, RESULT, TYPE, SEQ, PAY0, PAY1, LASTSEQ, BUSY = range(8)
CTR0 = 0x10
DESIGN_ID = 0x43505331           # "CPS1"
NONE, GOOD, BADCRC, SHORT, LONG, REPEAT, STALE, BADTYPE, BADLEN = range(9)
CTR_OF = {GOOD: 0, BADCRC: 1, SHORT: 2, LONG: 3, REPEAT: 4, STALE: 5, BADTYPE: 6, BADLEN: 6}
PAYLOAD_OF = {1: 2, 2: 6, 3: 0, 4: 2, 5: 0}


class Model:
    def __init__(self) -> None:
        self.cur = bytearray()
        self.last_wr = 0
        self.result, self.typ, self.seq = NONE, 0, 0
        self.p0 = self.p1 = 0
        self.last_seq, self.have = 0, 0
        self.ctr = [0] * 7

    def classify(self, p: bytes) -> int:
        if len(p) >= 4 and p[1] > 8:
            return LONG
        if len(p) >= 4 and len(p) > 8 + p[1]:
            return LONG
        if len(p) < 4 or len(p) < 8 + p[1]:
            return SHORT
        if zlib.crc32(p) != 0x2144DF1C:           # CRC of the packet with its own check appended
            return BADCRC
        if p[0] not in PAYLOAD_OF:
            return BADTYPE
        if p[1] != PAYLOAD_OF[p[0]]:
            return BADLEN
        if self.have:
            d = ((p[2] << 8 | p[3]) - self.last_seq) % 65536
            if d == 0:
                return REPEAT
            if d > 32767:
                return STALE
        return GOOD

    def write(self, off: int, v: int) -> None:
        if off != BYTE:
            return
        self.last_wr = v & 0x1FF
        self.cur.append(v & 0xFF)
        if v & 0x100:
            p, self.cur = bytes(self.cur), bytearray()
            c = self.classify(p)
            self.result = c
            self.ctr[CTR_OF.get(c, 6)] = (self.ctr[CTR_OF.get(c, 6)] + 1) & 0xFFFF
            if c == GOOD:
                self.typ, self.seq = p[0], p[2] << 8 | p[3]
                self.last_seq, self.have = self.seq, 1
                pay = p[4:-4] + bytes(6 - len(p[4:-4]))
                self.p0, self.p1 = int.from_bytes(pay[:2], "big"), int.from_bytes(pay[2:6], "big")

    def read(self, off: int) -> int:
        if CTR0 <= off < CTR0 + 7:
            return self.ctr[off - CTR0]
        return {BYTE: self.last_wr, RESULT: self.result, TYPE: self.typ, SEQ: self.seq, PAY0: self.p0, PAY1: self.p1,
                LASTSEQ: self.have << 16 | self.last_seq, BUSY: int(bool(self.cur))}.get(off, 0)

    def led(self) -> int:
        return (self.last_seq & 0xFF) << 8 | (self.ctr[0] & 0xFF)
