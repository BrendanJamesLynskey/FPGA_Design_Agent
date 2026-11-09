"""Reference model from the request (pure Python).

Only the arithmetic and the fixed shell constants are modelled. The request text does not list the
design's window register offsets, so no register map is modelled here.
"""

DESIGN_ID = int.from_bytes(b"DOTQ", "big")   # "four ASCII characters, MSB first" -> 0x444F5451
SHELL_VERSION = 0x00010000


def s32(x):
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x & 0x80000000 else x


def acc_of(acts, wts, bias):
    # "multiplies the eight pairs, adds the eight products and the bias"
    assert len(acts) == 8 and len(wts) == 8
    return s32(sum(a * w for a, w in zip(acts, wts)) + bias)


def requant(acc, mult, shift, relu):
    # scale by mult / 2^shift, round to nearest, exact halves toward +infinity, then clamp
    r = (acc * mult + (1 << (shift - 1))) >> shift   # floor(x + 1/2)
    lo = 0 if relu else -128
    return max(lo, min(127, r))


def dot_requant(acts, wts, bias, mult, shift, relu):
    acc = acc_of(acts, wts, bias)
    return requant(acc, mult, shift, relu), acc
