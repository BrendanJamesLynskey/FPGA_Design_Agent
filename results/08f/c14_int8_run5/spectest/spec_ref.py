"""Reference model of the quantised dot-product + requantise unit, from the request only."""

MASK32 = 0xFFFFFFFF

# Window register offsets (Q1 answer); the shell adds 0x80 to reach them.
WIN = 0x80
A_LO, A_HI, W_LO, W_HI, BIAS, MULT, CTRL, GO, Y, ACC, STATUS = range(0x80, 0x8B)

DESIGN_ID = 0x444F5451  # "DOTQ", MSB first (PROTOCOL.md: DESIGN_ID is ASCII MSB first)


def s8(v):
    v &= 0xFF
    return v - 256 if v & 0x80 else v


def s32(v):
    v &= MASK32
    return v - (1 << 32) if v & 0x80000000 else v


def pack8(vals):
    """Four signed bytes into a 32-bit word, element 0 in bits 7:0 (little-endian)."""
    return sum((v & 0xFF) << (8 * i) for i, v in enumerate(vals))


def compute(a, w, bias, mult, shift, relu):
    """a, w: 8 signed ints. Returns (y, acc) with y signed 8-bit."""
    acc = sum(x * k for x, k in zip(a, w)) + bias
    # "rounding to the nearest whole number with exact halves going up"
    scaled = (acc * mult + (1 << (shift - 1))) >> shift   # floor(x + 1/2), exact
    lo = 0 if relu else -128
    y = max(lo, min(127, scaled))
    return y, acc
