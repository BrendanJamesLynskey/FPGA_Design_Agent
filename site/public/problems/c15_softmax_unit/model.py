"""P15-2 model: the score sets and the float reference with the error budget (standalone: numpy only)."""
import numpy as np

N = 8
BUDGET = 1 / 128


def inputs():
    """330 deterministic sets of eight signed 16-bit Q8.8 scores."""
    rng = np.random.default_rng(15)
    cases = [[0] * N, [32767] + [-32768] * (N - 1), [-32768] * N, [1000] + [0] * (N - 1), list(range(0, N * 256, 256))]
    for scale in (0.5, 2.0, 6.0, 30.0):
        for _ in range(80):
            cases.append([int(v) for v in np.clip(np.round(rng.normal(0, scale, N) * 256), -32768, 32767)])
    base = cases[10]
    for off in (-20000, 20000, -777, 5000, 12000):                     # the same differences, shifted: the answer must not move
        cases.append([int(np.clip(v + off, -32768, 32767)) for v in base])
    return cases


def softmax_float(x):
    z = np.asarray(x, dtype=float) / 256.0
    e = np.exp(z - z.max())
    return e / e.sum()


def reference_output():
    """A perfect answer (the float result rounded to Q0.15)."""
    return {"p": [[int(round(v * 32768)) for v in softmax_float(x)] for x in inputs()]}


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x534D4158          # "SMAX"
X0, GO, STATUS, OUT0 = 0x00, 0x10, 0x11, 0x20


def bench_inputs():
    """30 of the course score sets: the five specials, 16 random across the four scales, the five shifted copies, and 4 more."""
    xs = inputs()
    return xs[:5] + xs[5:85:6] + xs[85:325:60] + xs[-5:]


def lanes_to_regs(v, bits=16):
    m = (1 << bits) - 1
    return [sum((v[i + k] & m) << (bits * k) for k in range(32 // bits) if i + k < len(v)) for i in range(0, len(v), 32 // bits)]
