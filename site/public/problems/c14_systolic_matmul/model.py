"""Reference model for P14-3 (4 x 4 matrix multiplier, rows in and out). Plain Python integers."""
import random

LATENCY = 7                    # clock edges between the edge that samples a row and the edge after which its results are visible with out_valid
MAX_LATENCY = 8                # what the spec allows


def weights():
    rng = random.Random(14)
    return [[rng.randint(-128, 127) for _ in range(4)] for _ in range(4)]


def rows():
    """The fixed test set: 40 rows applied on 40 consecutive clocks, then a second batch of 12 rows after a gap with new weights (weights2())."""
    rng = random.Random(15)
    r = [[rng.randint(-128, 127) for _ in range(4)] for _ in range(34)]
    r += [[-128] * 4, [127] * 4, [-128, 127, -128, 127], [0] * 4, [1, 0, 0, 0], [0, 0, 0, 1]]
    return r


def weights2():
    rng = random.Random(16)
    return [[rng.randint(-100, 100) for _ in range(4)] for _ in range(4)]


def rows2():
    rng = random.Random(17)
    return [[rng.randint(-128, 127) for _ in range(4)] for _ in range(12)]


def matmul(rs, W):
    return [[sum(a[i] * W[i][j] for i in range(4)) for j in range(4)] for a in rs]


def reference_output():
    return {"C": matmul(rows(), weights()), "C2": matmul(rows2(), weights2()), "latency_clocks": LATENCY, "accepted_every_clock": True}


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x4D4D3458          # "MM4X"
W0, LOAD, ROW0, BURST, STATUS, LAT, COUNT, RES0 = 0x00, 0x04, 0x08, 0x18, 0x19, 0x1A, 0x1B, 0x20


def pack_row(r):
    return sum((x & 0xFF) << (8 * i) for i, x in enumerate(r))


def s32(v):
    return v & 0xFFFFFFFF
