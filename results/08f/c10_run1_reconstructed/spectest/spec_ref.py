import math

N_SAMPLES = 1200
N_WORDS = N_SAMPLES // 2
DESIGN_ID = 0x4444534E  # "DDSN", MSB first (request + shell PROTOCOL DESIGN_ID rule)

# Window register offsets (request Q2 answer); shell address = 0x80 + offset
FW, GO, STATUS, PTR, DATA = 0x00, 0x01, 0x02, 0x03, 0x04


def table():
    # "entry i is floor(2047*sin(2*pi*i/256)+0.5)"
    return [math.floor(2047 * math.sin(2 * math.pi * i / 256) + 0.5) for i in range(256)]


TABLE = table()


def samples(fw, n=N_SAMPLES):
    """First sample is entry 0 (phase 0); phase advances by fw each clock,
    24-bit wrap, table addressed by the top 8 bits."""
    fw &= 0xFFFFFF
    out = []
    ph = 0
    for _ in range(n):
        out.append(TABLE[ph >> 16])
        ph = (ph + fw) & 0xFFFFFF
    return out


def word_samples(fw, m):
    s = samples(fw)
    return s[2 * m], s[2 * m + 1]


def to_signed12(v):
    v &= 0xFFF
    return v - 4096 if v >= 2048 else v


def unpack_data(word):
    """DATA: [11:0] sample 2m, [27:16] sample 2m+1 (two's complement 12 bit)."""
    return to_signed12(word), to_signed12(word >> 16)
