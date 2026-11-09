"""Reference model of the quantised-layer arithmetic unit, written from the request only."""

# Window offsets (request Q1 answer; the shell adds 0x80)
A_LO, A_HI, W_LO, W_HI, BIAS, MULT, CTRL, GO, Y, ACC, STATUS = range(0x00, 0x0B)
WINDOW = 0x80
DESIGN_ID = 0x444F5451  # "DOTQ", MSB first (shell protocol: four ASCII characters, MSB first)
CTRL_RESET = 1


def pack(lanes):
    """Four signed 8-bit lanes into a 32-bit word, lane 0 in bits 7:0."""
    v = 0
    for i, x in enumerate(lanes):
        v |= (x & 0xFF) << (8 * i)
    return v


def split_words(vals):
    return pack(vals[:4]), pack(vals[4:])


def ctrl_word(shift, relu):
    return (shift & 0x1F) | ((relu & 1) << 8)


def dot_acc(a, w, bias):
    # "multiplies the eight pairs, adds the eight products and the bias"
    return sum(x * y for x, y in zip(a, w)) + bias


def requant(acc, mult, shift, relu):
    # scale by mult / 2^shift, round to nearest with exact halves toward +infinity
    scaled = (acc * mult + (1 << (shift - 1))) >> shift  # arithmetic floor shift
    lo = 0 if relu else -128
    return max(lo, min(127, scaled))


def compute(a, w, bias, mult, shift, relu):
    acc = dot_acc(a, w, bias)
    return requant(acc, mult, shift, relu), acc
