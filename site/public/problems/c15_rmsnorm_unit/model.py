"""P15-3 model: the input vectors and the float reference with the error budget (standalone: numpy only)."""
import numpy as np

N = 16
BUDGET_LSB = 1.0


def inputs():
    rng = np.random.default_rng(16)
    cases = [[0] * N, [1] + [0] * (N - 1), [32767] * N, [-32768] * N, [32767, -32768] * (N // 2), [5] * N, [0] * (N - 1) + [-1]]
    for i in range(N):
        cases.append([0] * i + [20000] + [0] * (N - 1 - i))
    for scale in (0.01, 0.1, 1, 10, 60):
        for _ in range(250):
            cases.append([int(v) for v in np.clip(np.round(rng.normal(0, scale, N) * 256), -32768, 32767)])
    return cases


def rmsnorm_float(x):
    z = np.asarray(x, dtype=float)
    return z * 1024.0 / np.sqrt((z * z).sum() + 16)


def reference_output():
    return {"y": [[int(round(v)) for v in rmsnorm_float(x)] for x in inputs()]}


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x524D534E          # "RMSN"
X0, GO, STATUS, OUT0 = 0x00, 0x10, 0x11, 0x20


def bench_inputs():
    """The seven specials, four unit impulses (lane 0, 5, 9, 15), and 16 random vectors across the five scales."""
    xs = inputs()
    return xs[:7] + [xs[7], xs[12], xs[16], xs[22]] + xs[23:1273:80]


def lanes_to_regs(v, bits=16):
    m = (1 << bits) - 1
    return [sum((v[i + k] & m) << (bits * k) for k in range(32 // bits) if i + k < len(v)) for i in range(0, len(v), 32 // bits)]
