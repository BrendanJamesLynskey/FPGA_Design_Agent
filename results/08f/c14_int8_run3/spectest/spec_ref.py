"""Reference model for the quantised-layer arithmetic unit (from the request only)."""

# Window register offsets (Q1 answer); shell address = 0x80 + offset.
A_LO, A_HI, W_LO, W_HI, BIAS, MULT, CTRL, GO, Y, ACC, STATUS = range(0x0B)
WINDOW_BASE = 0x80  # shell/PROTOCOL.md: 0x80-0xFF is the design's window

DESIGN_ID = int.from_bytes(b"DOTQ", "big")  # four ASCII chars, MSB first


def s8(v):
    v &= 0xFF
    return v - 256 if v & 0x80 else v


def s32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


def pack_i8(vals):
    """Four int8 -> one 32-bit word, element 0 in bits 7:0."""
    assert len(vals) == 4
    return sum((v & 0xFF) << (8 * i) for i, v in enumerate(vals))


def ctrl_word(shift, relu):
    """CTRL: shift [4:0], relu [8]."""
    return (shift & 0x1F) | ((relu & 1) << 8)


def dot(a, w, bias):
    """acc = sum of eight products plus bias (caller keeps it inside int32)."""
    assert len(a) == 8 and len(w) == 8
    return sum(x * y for x, y in zip(a, w)) + bias


def requant(acc, mult, shift, relu):
    """acc * mult / 2^shift, nearest, exact halves toward +infinity, then limit."""
    r = (acc * mult + (1 << (shift - 1))) >> shift  # floor(x + 1/2)
    lo = 0 if relu else -128
    return max(lo, min(127, r))


def expected(a, w, bias, mult, shift, relu):
    acc = dot(a, w, bias)
    assert -(1 << 31) <= acc < (1 << 31)
    return requant(acc, mult, shift, relu), acc
