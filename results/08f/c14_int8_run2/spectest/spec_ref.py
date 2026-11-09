"""Reference model for the quantised-layer arithmetic unit (from the request only)."""

MASK32 = 0xFFFFFFFF

# Window offsets (Q1); the shell address is 0x80 + offset.
A_LO, A_HI, W_LO, W_HI, BIAS, MULT, CTRL, GO, Y, ACC, STATUS = range(11)
WINDOW_BASE = 0x80

DESIGN_ID = int.from_bytes(b"DOTQ", "big")   # four ASCII chars, MSB first (shell spec)


def s32(x):
    x &= MASK32
    return x - (1 << 32) if x & 0x80000000 else x


def s8(x):
    x &= 0xFF
    return x - 256 if x & 0x80 else x


def pack4(vals):
    """Four signed 8-bit numbers, element 0 in bits 7:0 (little-endian packing assumed)."""
    w = 0
    for i, v in enumerate(vals):
        w |= (v & 0xFF) << (8 * i)
    return w


def acc_of(a, w, bias):
    # "multiplies the eight pairs, adds the eight products and the bias"; 32-bit signed
    return s32(sum(x * y for x, y in zip(a, w)) + bias)


def requant(acc, mult, shift, relu):
    # scale by mult / 2**shift, nearest, exact halves toward +infinity
    r = (acc * mult + (1 << (shift - 1))) >> shift   # python >> floors
    lo = 0 if relu else -128
    return max(lo, min(127, r))


def expected(a, w, bias, mult, shift, relu):
    acc = acc_of(a, w, bias)
    return requant(acc, mult, shift, relu), acc


def ctrl_word(shift, relu):
    return (shift & 0x1F) | ((relu & 1) << 8)
