"""Reference model for P9-3 (3 x 3 median of nine 8-bit pixels). Standalone: python only."""
import random


def windows(seed=33, n_random=100, n_equal=60, n_outlier=60, n_runs=40):
    rng = random.Random(seed)
    ws = [[rng.randrange(256) for _ in range(9)] for _ in range(n_random)]
    ws += [[v] * 9 for v in (0, 1, 127, 128, 254, 255)]
    ws += [[0] * 4 + [255] * 5, [255] * 4 + [0] * 5, [0] * 9, [255] * 8 + [0], [0] * 8 + [255]]
    for _ in range(n_outlier):
        base = rng.randrange(256)
        w = [min(255, max(0, base + rng.randrange(-3, 4))) for _ in range(9)]
        w[rng.randrange(9)] = rng.choice((0, 255))
        ws.append(w)
    for _ in range(n_runs):
        ws.append([rng.choice((0, 255, 17)) for _ in range(9)])
    for _ in range(n_equal):
        base = rng.randrange(256)
        w = [base] * 9
        for k in rng.sample(range(9), rng.randrange(1, 5)):
            w[k] = rng.randrange(256)
        ws.append(w)
    return ws


def median(w):
    return sorted(w)[4]


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x4D45444E          # "MEDN"
MASK, GO, STATUS, NOUT, VMASK = 0x00, 0x01, 0x02, 0x03, 0x04
WIN, MED = 0x10, 0x30
LAT = 1


def pack_win(w):
    """Three register words: pixels 0..2, 3..5, 6..8, pixel p in bits [8p+7:8p] of its word."""
    return [sum(w[3 * r + p] << (8 * p) for p in range(3)) for r in range(3)]
