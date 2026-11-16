"""Golden model of the endpoint, from spec.yaml only: a packet in, the reply (or nothing) out, and the state it leaves."""

from __future__ import annotations

import zlib

IN, TICK, RLEN, RIDX, RWORD, TLEN, TIDX, TWORD, TAKE, STAT = range(10)
DESIGN_ID = 0x55455031           # "UEP1"
NEED = {1: 2, 2: 6, 3: 0, 4: 2, 5: 0}
OKC, BADCRC, SHORT, LONG, REPEAT, STALE, PROTO = range(7)
GOOD_CRC = 0x2144DF1C


def frame(typ: int, status: int, seq: int, pay: bytes = b"") -> bytes:
    head = bytes([typ | 0x80, status, seq >> 8, seq & 0xFF, len(pay)]) + pay
    return head + zlib.crc32(head).to_bytes(4, "little")


class Model:
    def __init__(self) -> None:
        self.cur = bytearray()
        self.scratch = [0, 0, 0]
        self.n = [0] * 7
        self.last, self.have = 0, 0
        self.period, self.on, self.cnt, self.up = 100, 0, 0, 0
        self.tseq = self.tframes = 0
        self.held = b""
        self.reply = b""
        self.ridx = self.tidx = 0

    @property
    def refused(self) -> int:
        return sum(self.n[1:])

    def regval(self, a: int) -> int:
        return [0x55445031, *self.scratch, self.n[0], self.refused, self.period, self.up][a] & 0xFFFFFFFF

    def packet(self, p: bytes) -> bytes:
        self.reply = b""
        if len(p) >= 4 and (p[1] > 8 or len(p) > 8 + p[1]):
            self.n[LONG] += 1
            return b""
        if len(p) < 4 or len(p) < 8 + p[1]:
            self.n[SHORT] += 1
            return b""
        if zlib.crc32(p) != GOOD_CRC:
            self.n[BADCRC] += 1
            return b""
        typ, seq, pay = p[0], p[2] << 8 | p[3], p[4:-4]
        if typ not in NEED:
            self.n[PROTO] += 1
            return frame(typ, 1, seq)
        if p[1] != NEED[typ]:
            self.n[PROTO] += 1
            return frame(typ, 2, seq)
        if self.have:
            d = (seq - self.last) % 65536
            if d == 0 or d >= 32768:
                self.n[REPEAT if d == 0 else STALE] += 1
                return frame(typ, 4, seq)
        self.last, self.have = seq, 1
        a = int.from_bytes(pay[:2], "big")
        if typ in (1, 2) and (a > 7 or (typ == 2 and a not in (1, 2, 3))):
            self.n[PROTO] += 1
            return frame(typ, 3 if a > 7 else 5, seq)
        body = b""
        if typ == 1:
            body = self.regval(a).to_bytes(4, "big")
        elif typ == 2:
            self.scratch[a - 1] = int.from_bytes(pay[2:6], "big")
        elif typ == 3:
            body = b"".join((v & 0xFFFF).to_bytes(2, "big") for v in self.n) + (self.tframes & 0xFFFF).to_bytes(2, "big") + bytes([self.on])
        elif typ == 4:
            self.on, self.cnt = 1, 0
            if a:
                self.period = max(a, 4)
        else:
            self.on, self.held = 0, b""
        self.n[OKC] += 1
        return frame(typ, 0, seq, body)

    def write(self, off: int, v: int) -> None:
        if off == IN:
            self.cur.append(v & 0xFF)
            if v & 0x100:
                p, self.cur = bytes(self.cur), bytearray()
                self.reply = self.packet(p)
        elif off == TICK:
            for _ in range(v & 0xFF):
                self.up = (self.up + 1) & 0xFFFFFFFF
                if self.on:
                    self.cnt += 1
                    if self.cnt >= self.period:
                        self.cnt = 0
                        if not self.held:
                            head = bytes([0xC0, 0, self.tseq >> 8 & 0xFF, self.tseq & 0xFF, 8]) + self.up.to_bytes(4, "big") \
                                + (self.n[0] & 0xFFFF).to_bytes(2, "big") + (self.refused & 0xFFFF).to_bytes(2, "big")
                            self.held = head + zlib.crc32(head).to_bytes(4, "little")
                            self.tseq, self.tframes = self.tseq + 1, self.tframes + 1
        elif off == TAKE:
            self.held = b""
        elif off == RIDX:
            self.ridx = v & 0x7F
        elif off == TIDX:
            self.tidx = v & 0x7F

    @staticmethod
    def word(buf: bytes, i: int) -> int:
        return int.from_bytes((buf + bytes(4 * 128))[4 * i:4 * i + 4], "big")

    def read(self, off: int) -> int:
        return {RLEN: len(self.reply), RIDX: self.ridx, RWORD: self.word(self.reply, self.ridx),
                TLEN: len(self.held), TIDX: self.tidx, TWORD: self.word(self.held, self.tidx),
                STAT: self.on}.get(off, 0)
