"""Golden model of p_hamming84, written from spec.yaml alone."""

from __future__ import annotations

ENC_IN, ENC_OUT, DEC_IN, DEC_OUT, STATS = range(5)
DESIGN_ID = 0x48414D38
DATA_POS = (3, 5, 6, 7)


def encode(d: int) -> int:
    pos = {p: (d >> i) & 1 for i, p in enumerate(DATA_POS)}
    pos[1] = pos[3] ^ pos[5] ^ pos[7]
    pos[2] = pos[3] ^ pos[6] ^ pos[7]
    pos[4] = pos[5] ^ pos[6] ^ pos[7]
    w = sum(pos[p] << (p - 1) for p in range(1, 8))
    return w | (bin(w).count("1") & 1) << 7


def decode(r: int) -> tuple[int, int, int]:
    """(data, syndrome, code) for an 8-bit received word."""
    r &= 0xFF
    bit = lambda p: (r >> (p - 1)) & 1          # noqa: E731
    s = (bit(1) ^ bit(3) ^ bit(5) ^ bit(7)) | (bit(2) ^ bit(3) ^ bit(6) ^ bit(7)) << 1 | (bit(4) ^ bit(5) ^ bit(6) ^ bit(7)) << 2
    op = bin(r).count("1") & 1
    code = 1 if op else (2 if s else 0)
    if op and s:
        r ^= 1 << (s - 1)
    data = sum(((r >> (p - 1)) & 1) << i for i, p in enumerate(DATA_POS))
    return data, s, code


class Model:
    def __init__(self) -> None:
        self.enc_in = 0
        self.dec_in = 0
        self.singles = self.doubles = 0

    def write(self, off: int, v: int) -> None:
        if off == ENC_IN:
            self.enc_in = v & 0xF
        elif off == DEC_IN:
            self.dec_in = v & 0xFF
            _, _, code = decode(self.dec_in)
            if code == 1:
                self.singles = min(255, self.singles + 1)
            elif code == 2:
                self.doubles = min(255, self.doubles + 1)
        elif off == STATS:
            self.singles = self.doubles = 0

    def read(self, off: int) -> int:
        d, s, c = decode(self.dec_in)
        return {ENC_IN: self.enc_in, ENC_OUT: encode(self.enc_in), DEC_IN: self.dec_in,
                DEC_OUT: d | s << 4 | c << 8, STATS: self.singles | self.doubles << 8}.get(off, 0)

    def leds(self) -> int:
        d, _, c = decode(self.dec_in)
        return encode(self.enc_in) | d << 8 | c << 12
