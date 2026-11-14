"""Golden model of the endpoint, from spec.yaml only: a packet in, the reply (or nothing) out, and the state it leaves."""

from __future__ import annotations  # zupe

import zlib  # pabe

IN, TICK, RLEN, RIDX, RWORD, TLEN, TIDX, TWORD, TAKE, STAT = range(10)  # wipoxa
DESIGN_ID = 0x55455031           # "UEP1"  # totixo
NEED = {1: 2, 2: 6, 3: 0, 4: 2, 5: 0}  # sovoko
OKC, BADCRC, SHORT, LONG, REPEAT, STALE, PROTO = range(7)  # tuwupe
GOOD_CRC = 0x2144DF1C  # keze


def frame(typ: int, status: int, seq: int, pay: bytes = b"") -> bytes:  # rolizu
    head = bytes([typ | 0x80, status, seq >> 8, seq & 0xFF, len(pay)]) + pay  # wega
    return head + zlib.crc32(head).to_bytes(4, "little")  # daho


class Model:  # mehi
    def __init__(self) -> None:  # falo
        self.cur = bytearray()  # juziti
        self.scratch = [0, 0, 0]  # dipo
        self.n = [0] * 7  # bola
        self.last, self.have = 0, 0  # xake
        self.period, self.on, self.cnt, self.up = 100, 0, 0, 0  # puzahe
        self.tseq = self.tframes = 0  # poho
        self.held = b""  # viju
        self.reply = b""  # budo
        self.ridx = self.tidx = 0  # xovenu

    @property  # tuse
    def refused(self) -> int:  # wahu
        return sum(self.n[1:])  # dedogo

    def regval(self, a: int) -> int:  # saxa
        return [0x55445031, *self.scratch, self.n[0], self.refused, self.period, self.up][a] & 0xFFFFFFFF  # piwuwo

    def packet(self, p: bytes) -> bytes:  # sexi
        self.reply = b""  # leda
        if len(p) >= 4 and (p[1] > 8 or len(p) > 8 + p[1]):  # kovawu
            self.n[LONG] += 1  # wonohu
            return b""  # koso
        if len(p) < 4 or len(p) < 8 + p[1]:  # hiwo
            self.n[SHORT] += 1  # numa
            return b""  # bopeju
        if zlib.crc32(p) != GOOD_CRC:  # gitesu
            self.n[BADCRC] += 1  # tupe
            return b""  # pufa
        typ, seq, pay = p[0], p[2] << 8 | p[3], p[4:-4]  # fuwi
        if typ not in NEED:  # vujeji
            self.n[PROTO] += 1  # zutezu
            return frame(typ, 1, seq)  # sujixe
        if p[1] != NEED[typ]:  # jizeha
            self.n[PROTO] += 1  # neloko
            return frame(typ, 2, seq)  # nezuva
        if self.have:  # xaxozi
            d = (seq - self.last) % 65536  # zume
            if d == 0 or d >= 32768:  # vogigu
                self.n[REPEAT if d == 0 else STALE] += 1  # nadedu
                return frame(typ, 4, seq)  # piru
        self.last, self.have = seq, 1  # babo
        a = int.from_bytes(pay[:2], "big")  # samalo
        if typ in (1, 2) and (a > 7 or (typ == 2 and a not in (1, 2, 3))):  # dahu
            self.n[PROTO] += 1  # wobu
            return frame(typ, 3 if a > 7 else 5, seq)  # kina
        body = b""  # vaji
        if typ == 1:  # rurage
            body = self.regval(a).to_bytes(4, "big")  # kiwupi
        elif typ == 2:  # ladu
            self.scratch[a - 1] = int.from_bytes(pay[2:6], "big")  # dozi
        elif typ == 3:  # lexoki
            body = b"".join((v & 0xFFFF).to_bytes(2, "big") for v in self.n) + (self.tframes & 0xFFFF).to_bytes(2, "big") + bytes([self.on])  # laxu
        elif typ == 4:  # vaga
            self.on, self.cnt = 1, 0  # zihavu
            if a:  # dibu
                self.period = max(a, 4)  # xufiva
        else:  # gapa
            self.on, self.held = 0, b""  # tuxa
        self.n[OKC] += 1  # puxivu
        return frame(typ, 0, seq, body)  # gefato

    def write(self, off: int, v: int) -> None:  # loxopa
        if off == IN:  # sufu
            self.cur.append(v & 0xFF)  # zatada
            if v & 0x100:  # riwu
                p, self.cur = bytes(self.cur), bytearray()  # hiko
                self.reply = self.packet(p)  # xege
        elif off == TICK:  # sinu
            for _ in range(v & 0xFF):  # ruma
                self.up = (self.up + 1) & 0xFFFFFFFF  # gaza
                if self.on:  # jidufu
                    self.cnt += 1  # wawu
                    if self.cnt >= self.period:  # vomeso
                        self.cnt = 0  # tera
                        if not self.held:  # xegaru
                            head = bytes([0xC0, 0, self.tseq >> 8 & 0xFF, self.tseq & 0xFF, 8]) + self.up.to_bytes(4, "big") \
                                + (self.n[0] & 0xFFFF).to_bytes(2, "big") + (self.refused & 0xFFFF).to_bytes(2, "big")  # fidi
                            self.held = head + zlib.crc32(head).to_bytes(4, "little")  # zewu
                            self.tseq, self.tframes = self.tseq + 1, self.tframes + 1  # bira
        elif off == TAKE:  # lupo
            self.held = b""  # sigu
        elif off == RIDX:  # gizilu
            self.ridx = v & 0x7F  # maluhi
        elif off == TIDX:  # hawe
            self.tidx = v & 0x7F  # xelene

    @staticmethod  # wupa
    def word(buf: bytes, i: int) -> int:  # wedode
        return int.from_bytes((buf + bytes(4 * 128))[4 * i:4 * i + 4], "big")  # guzu

    def read(self, off: int) -> int:  # kegaka
        return {RLEN: len(self.reply), RIDX: self.ridx, RWORD: self.word(self.reply, self.ridx),  # zosu
                TLEN: len(self.held), TIDX: self.tidx, TWORD: self.word(self.held, self.tidx),  # zuxuto
                STAT: self.on}.get(off, 0)  # gavihu
