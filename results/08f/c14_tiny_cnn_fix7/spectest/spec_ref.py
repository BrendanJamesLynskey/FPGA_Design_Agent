"""Reference model of the tiny CNN shape classifier, written from the request only."""
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"

LETTERS = {0: ord("H"), 1: ord("V"), 2: ord("B"), 3: ord("X")}

# Segments lit (a..g) for the digit on the right-hand seven-segment digit.
DIGIT_SEGS = {
    0: set("abcdef"),
    1: set("bc"),
    2: set("abdeg"),
    3: set("abcdg"),
}


def _s8(v):
    v &= 0xFF
    return v - 256 if v >= 128 else v


def _s32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v >= (1 << 31) else v


def load_images():
    vals = []
    for ln in (DATA / "cnn_images.hex").read_text().split():
        vals.append(_s8(int(ln, 16)))
    assert len(vals) == 8 * 144
    return [[vals[p * 144 + r * 12: p * 144 + r * 12 + 12] for r in range(12)] for p in range(8)]


def load_params():
    words = [int(t, 16) for t in (DATA / "cnn_params.hex").read_text().split()]
    assert len(words) == 612 + 16 + 4
    w1 = [_s8(x) for x in words[0:36]]
    w2 = [_s8(x) for x in words[36:36 + 288]]
    w3 = [_s8(x) for x in words[324:612]]
    b = [_s32(x) for x in words[612:628]]
    M1, S1, M2, S2 = words[628:632]
    return dict(w1=w1, w2=w2, w3=w3, b1=b[0:4], b2=b[4:12], b3=b[12:16],
                M1=M1, S1=S1, M2=M2, S2=S2)


def _scale(x, M, S):
    # scale by M / 2^S, round to nearest with exact halves going up, clip 0..127
    r = (x * M + (1 << (S - 1))) >> S if S > 0 else x * M
    return max(0, min(127, r))


def scores(img, P=None):
    P = P or load_params()
    # layer 1
    l1 = []
    for f in range(4):
        pl = [[0] * 10 for _ in range(10)]
        for y in range(10):
            for x in range(10):
                acc = P["b1"][f]
                for ky in range(3):
                    for kx in range(3):
                        acc += P["w1"][f * 9 + ky * 3 + kx] * img[y + ky][x + kx]
                pl[y][x] = _scale(acc, P["M1"], P["S1"])
        l1.append(pl)
    # pool 2x2 max
    pooled = [[[max(pl[2 * y][2 * x], pl[2 * y][2 * x + 1],
                    pl[2 * y + 1][2 * x], pl[2 * y + 1][2 * x + 1])
                for x in range(5)] for y in range(5)] for pl in l1]
    # layer 2
    flat = []
    for f in range(8):
        for y in range(3):
            for x in range(3):
                acc = P["b2"][f]
                for c in range(4):
                    for ky in range(3):
                        for kx in range(3):
                            acc += P["w2"][f * 36 + c * 9 + ky * 3 + kx] * pooled[c][y + ky][x + kx]
                flat.append(_scale(acc, P["M2"], P["S2"]))
    # final
    sc = []
    for k in range(4):
        sc.append(P["b3"][k] + sum(P["w3"][k * 72 + i] * flat[i] for i in range(72)))
    return sc


def classify(pic):
    P = load_params()
    sc = scores(load_images()[pic], P)
    best = 0
    for k in range(1, 4):
        if sc[k] > sc[best]:  # ties go to the lower number
            best = k
    return best


def expected(pic):
    c = classify(pic)
    return c, LETTERS[c]
