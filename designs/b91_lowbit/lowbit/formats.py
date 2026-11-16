"""The weight formats of brief 91. A format is a set of non-negative integer magnitudes (the "element grid") and a
sign. A weight of a neuron is c * e, where e is a signed element and c = 2^-sh is the neuron's shared power-of-two
scale (the MX block scale: the block is the neuron's whole weight row, at most 16 weights, which is below the OCP MX
block size of 32). Because c is a power of two, the scale is not a multiplier: it is the neuron's requantisation shift
(model.py). All grids are in integer element units, so the accumulator is an exact integer.

    name      mags (element units)                              notes
    binary    1                                                 sign only, no zero: e = +1 or -1
    ternary   0 1
    int4      0 1 2 3 4 5 6 7                                   symmetric, -8 unused
    mxfp4     0 1 2 3 4 6 8 12                                  OCP E2M1 magnitudes 0 .5 1 1.5 2 3 4 6, times 2
    log4      0 1 2 4 8 16 32 64                                sign + 3-bit exponent code; code 0 = zero
    log4_nz   1 2 4 8 16 32 64 128                              sign + 3-bit exponent, no zero
    log4p1    0 2 3 4 6 8 12 16 24 32 48 64 96 128 192 256     sign + 3-bit exponent + 1-bit mantissa (5 bits),
                                                                magnitude 2^e (1 + m/2) times 2; code 0 = zero;
                                                                1.5 * 2^7 is not coded (15 levels + zero)

Rounding: nearest element in the linear domain; a tie goes to the element with the even code index (the OCP MX
requirement is roundTiesToEven; for log4 and log4p1 the code index is the exponent or exponent-mantissa code). A value
beyond the largest element saturates (clamps) to it. A value below half the smallest non-zero element rounds to zero
when the format has a zero, and to the smallest element when it has none. The sign of a value is its sign; zero in a
format with no zero code takes +.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MAGS = {
    "binary": (1,),
    "ternary": (0, 1),
    "int4": (0, 1, 2, 3, 4, 5, 6, 7),
    "mxfp4": (0, 1, 2, 3, 4, 6, 8, 12),
    "log4": (0, 1, 2, 4, 8, 16, 32, 64),
    "log4_nz": (1, 2, 4, 8, 16, 32, 64, 128),
    "log4p1": (0, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256),
}
WEIGHT_BITS = {"binary": 1, "ternary": 2, "int4": 4, "mxfp4": 4, "log4": 4, "log4_nz": 4, "log4p1": 5}
FAMILY = {"binary": "binary", "binary_t3": "binary", "binary_t7": "binary", "ternary": "ternary", "int4": "int4",
          "mxfp4": "mxfp4", "log4": "log4", "log4_nz": "log4", "log4p1": "log4p1"}


@dataclass(frozen=True)
class Fmt:
    name: str
    mags: tuple

    @property
    def has_zero(self):
        return self.mags[0] == 0

    @property
    def binary(self):
        return self.name == "binary"

    @property
    def max_mag(self):
        return self.mags[-1]

    def midpoints(self):
        return [(a + b) / 2 for a, b in zip(self.mags[:-1], self.mags[1:])]


def get(name: str) -> Fmt:
    base = "binary" if name.startswith("binary") else name
    return Fmt(base, MAGS[base])


def quantize_np(u: np.ndarray, f: Fmt) -> np.ndarray:
    """Real values (element units) -> signed integer elements. Ties to the even code index; saturating."""
    u = np.asarray(u, dtype=np.float64)
    a = np.abs(u)
    idx = np.zeros(a.shape, dtype=np.int64)
    for i, m in enumerate(f.midpoints()):
        idx += (a > m) | ((a == m) & ((i + 1) % 2 == 0))
    mags = np.array(f.mags, dtype=np.int64)
    sgn = np.where(u < 0, -1, 1)
    return sgn * mags[idx]


def quantize_t(u, f: Fmt):
    """The same function on a torch tensor (no gradient; the caller adds the straight-through term)."""
    import torch
    a = u.abs()
    idx = torch.zeros(a.shape, dtype=torch.long)
    for i, m in enumerate(f.midpoints()):
        idx += ((a > m) | ((a == m) & ((i + 1) % 2 == 0))).long()
    mags = torch.tensor(f.mags, dtype=u.dtype)
    sgn = torch.where(u < 0, -torch.ones_like(u), torch.ones_like(u))
    return sgn * mags[idx]


def csd(n: int) -> list[tuple[int, int]]:
    """Non-adjacent signed-digit form of an integer: [(sign, shift)] with sum(sign * 2^shift) = n. Fewest terms."""
    out, s = [], 0
    while n != 0:
        if n & 1:
            d = 2 - (n & 3)          # +1 if n mod 4 == 1, -1 if n mod 4 == 3
            out.append((d, s))
            n -= d
        n >>= 1
        s += 1
    return out
