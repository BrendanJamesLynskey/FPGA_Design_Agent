"""Reference model of the fabric PRBS (rtl/prbs64.sv): x^n + x^k + 1, 64 bits per word, bit 0 first.

The state is an integer whose bit 0 is the newest bit; each step computes new = s[n-1] ^ s[k-1] and shifts it in.
Independent of the RTL: the sequence is also checked against the polynomial's maximal period (2^n - 1) in the tests.
"""

from __future__ import annotations

POLY = {0: (7, 6), 1: (15, 14), 2: (23, 18), 3: (31, 28)}   # sel -> (n, k)
NAME = {0: "PRBS-7", 1: "PRBS-15", 2: "PRBS-23", 3: "PRBS-31"}
SEED = 0x7FFFFFFF


def bits(sel: int, count: int, state: int = SEED) -> list[int]:
    n, k = POLY[sel]
    mask = (1 << n) - 1
    out = []
    s = state & mask
    for _ in range(count):
        nb = ((s >> (n - 1)) ^ (s >> (k - 1))) & 1
        s = ((s << 1) | nb) & mask
        out.append(nb)
    return out


def words(sel: int, count: int) -> list[int]:
    """The first `count` 64-bit words the generator sends after a reset (state all ones, masked to n bits)."""
    b = bits(sel, 64 * count)
    return [sum(b[64 * w + i] << i for i in range(64)) for w in range(count)]


def period(sel: int) -> int:
    """Sequence period by stepping until the state repeats (2^n - 1 for a maximal polynomial)."""
    n, k = POLY[sel]
    mask = (1 << n) - 1
    s0 = SEED & mask
    s = s0
    for i in range(1, (1 << n) + 1):
        nb = ((s >> (n - 1)) ^ (s >> (k - 1))) & 1
        s = ((s << 1) | nb) & mask
        if s == s0:
            return i
    return -1
