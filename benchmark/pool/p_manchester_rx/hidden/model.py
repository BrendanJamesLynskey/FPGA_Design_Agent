"""Golden model of p_manchester_rx, written from spec.yaml alone."""

from __future__ import annotations

DATA, GOOD, E_CODING, E_PREAMBLE, E_PARITY, CTRL = range(6)
DESIGN_ID = 0x4D435258


def wave(bits: list[int], bit_cycles: int) -> list[int]:
    """Line levels for a bit list: 1 = low then high, 0 = high then low."""
    h = bit_cycles // 2
    out: list[int] = []
    for b in bits:
        out += [0] * h + [1] * h if b else [1] * h + [0] * h
    return out


def frame(byte: int, parity_flip: bool = False) -> list[int]:
    d = [(byte >> i) & 1 for i in range(8)]
    return [1, 1, 1, 1, 0] + d + [(sum(d) & 1) ^ int(parity_flip)]


def classify(bits: list[int], bit_cycles: int, drop_transition: int | None = None):
    """Decode the bit list sent on a line (optionally with bit `drop_transition` made flat). Returns ('good', byte),
    ('coding',), ('preamble',) or ('parity',)."""
    h = bit_cycles // 2
    line = []
    for j, b in enumerate(bits):
        first, second = (0, 1) if b else (1, 0)
        if j == drop_transition:
            first = second
        line += [first] * h + [second] * h
    q = bit_cycles // 4
    got = []
    for j in range(len(bits)):
        f, s = line[j * bit_cycles + h - q], line[j * bit_cycles + h + q]
        if f == s:
            return ("coding",)
        got.append(s)
    if got[:5] != [1, 1, 1, 1, 0]:
        return ("preamble",)
    d = got[5:13]
    if (sum(d) + got[13]) & 1:
        return ("parity",)
    return ("good", sum(b << i for i, b in enumerate(d)))


class Model:
    def __init__(self, bit_cycles: int) -> None:
        self.bc = bit_cycles
        self.data = self.good = 0
        self.e = {"coding": 0, "preamble": 0, "parity": 0}

    def receive(self, bits: list[int], drop_transition: int | None = None) -> tuple:
        r = classify(bits, self.bc, drop_transition)
        if r[0] == "good":
            self.data, self.good = r[1], (self.good + 1) & 0xFF
        else:
            self.e[r[0]] = min(255, self.e[r[0]] + 1)
        return r

    def read(self, off: int) -> int:
        return {DATA: self.data, GOOD: self.good, E_CODING: self.e["coding"], E_PREAMBLE: self.e["preamble"], E_PARITY: self.e["parity"]}.get(off, 0)

    def write(self, off: int, v: int) -> None:
        if off == CTRL:
            self.good = 0
            self.e = {"coding": 0, "preamble": 0, "parity": 0}

    def leds(self) -> int:
        return self.data | self.good << 8
