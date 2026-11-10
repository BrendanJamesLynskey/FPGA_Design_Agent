"""Reference model for P14-2 (int8 dot product with requantisation). Plain Python integers, no dependencies."""
import random

N = 8


def requant(acc, mult, shift):
    return (acc * mult + (1 << (shift - 1))) >> shift          # Python >> on a negative int is the arithmetic (floor) shift


def compute(a, w, bias, mult, shift, relu):
    acc = sum(x * y for x, y in zip(a, w)) + bias
    y = max(0 if relu else -128, min(127, requant(acc, mult, shift)))
    return acc, y


def vectors():
    """The fixed test set (400 cases): random cases, then extremes, exact halves and both saturations. The agent's testbench must apply these in this order."""
    rng = random.Random(5)
    cases = []
    for _ in range(300):
        cases.append(dict(a=[rng.randint(-128, 127) for _ in range(N)], w=[rng.randint(-127, 127) for _ in range(N)], bias=rng.randint(-5000, 5000),
                          mult=rng.randint(1 << 14, (1 << 16) - 1), shift=rng.randint(8, 26), relu=rng.randint(0, 1)))
    big, small = [127] * N, [-128] * N
    for a, w in ((small, small), (big, big), (big, small)):
        for relu in (0, 1):
            cases.append(dict(a=a, w=w, bias=0, mult=65535, shift=15, relu=relu))
    for acc in (1, 3, -1, -3, 5, -5):
        cases.append(dict(a=[acc] + [0] * (N - 1), w=[1] + [0] * (N - 1), bias=0, mult=1, shift=1, relu=0))
    cases.append(dict(a=[0] * N, w=[0] * N, bias=-1, mult=40000, shift=16, relu=0))
    cases.append(dict(a=[0] * N, w=[0] * N, bias=2 ** 31 - 1 - 100, mult=1, shift=1, relu=0))
    while len(cases) < 400:
        cases.append(dict(a=[rng.choice((-128, 127)) for _ in range(N)], w=[rng.choice((-127, 127)) for _ in range(N)], bias=rng.choice((-10 ** 6, 10 ** 6)),
                          mult=rng.randint(1 << 14, (1 << 16) - 1), shift=rng.randint(8, 26), relu=rng.randint(0, 1)))
    return cases


def reference_output():
    out = []
    for c in vectors():
        acc, y = compute(**c)
        out.append({"acc": acc, "y": y})
    return {"cases": out}


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x444F5451          # "DOTQ"
A_LO, A_HI, W_LO, W_HI, BIAS, MULT, CTRL, GO, Y, ACC, STATUS = range(11)


def pack8(v):
    return sum((x & 0xFF) << (8 * i) for i, x in enumerate(v))

