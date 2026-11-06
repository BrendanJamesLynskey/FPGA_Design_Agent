"""P16-3 model: the number-theoretic transform of ML-KEM (FIPS 203 algorithms 9 and 10, q = 3329, 256 coefficients) and the transforms the block is asked for (standalone: python only)."""
import hashlib
import math
import random
import struct


Q = 3329


def bitrev7(i: int) -> int:
    return int(format(i, "07b")[::-1], 2)


ZETAS = [pow(17, bitrev7(i), Q) for i in range(128)]     # FIPS 203 Appendix A: 1, 1729, 2580, 3289, ...


def ntt(f: list[int]) -> list[int]:
    """FIPS 203 algorithm 9."""
    f = list(f)
    k, ln = 1, 128
    while ln >= 2:
        for start in range(0, 256, 2 * ln):
            z = ZETAS[k]
            k += 1
            for j in range(start, start + ln):
                t = z * f[j + ln] % Q
                f[j + ln] = (f[j] - t) % Q
                f[j] = (f[j] + t) % Q
        ln >>= 1
    return f


def intt(f: list[int]) -> list[int]:
    """FIPS 203 algorithm 10."""
    f = list(f)
    k, ln = 127, 2
    while ln <= 128:
        for start in range(0, 256, 2 * ln):
            z = ZETAS[k]
            k -= 1
            for j in range(start, start + ln):
                t = f[j]
                f[j] = (t + f[j + ln]) % Q
                f[j + ln] = z * (f[j + ln] - t) % Q
        ln <<= 1
    return [x * 3303 % Q for x in f]


def poly_mul_negacyclic(a: list[int], b: list[int]) -> list[int]:
    """Schoolbook product modulo x^256 + 1 (the ring of ML-KEM), the reference for the NTT's purpose."""
    r = [0] * 256
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            k = i + j
            if k < 256:
                r[k] = (r[k] + x * y) % Q
            else:
                r[k - 256] = (r[k - 256] - x * y) % Q
    return r


def basecase_mul(a_hat: list[int], b_hat: list[int]) -> list[int]:
    """FIPS 203 algorithm 11 (MultiplyNTTs): 128 degree-1 products modulo x^2 - zeta^(2 bitrev7(i) + 1)."""
    h = [0] * 256
    for i in range(128):
        g = pow(17, 2 * bitrev7(i) + 1, Q)
        a0, a1, b0, b1 = a_hat[2 * i], a_hat[2 * i + 1], b_hat[2 * i], b_hat[2 * i + 1]
        h[2 * i] = (a0 * b0 + a1 * b1 % Q * g) % Q
        h[2 * i + 1] = (a0 * b1 + a1 * b0) % Q
    return h


def polys():
    rng = random.Random(18)
    return [[0] * 256, [1] + [0] * 255, [Q - 1] * 256, [rng.randrange(Q) for _ in range(256)], [rng.randrange(Q) for _ in range(256)]]


def reference_output():
    cases = []
    for p in polys():
        cases.append({"op": "forward", "input": p, "output": ntt(p), "clocks": 896})
    for p in polys()[3:]:
        cases.append({"op": "inverse", "input": p, "output": intt(p), "clocks": 1152})
    return {"cases": cases}


# ---- benchmark wrapper: the shell register map (from spec.yaml) ----
DESIGN_ID = 0x4E545445          # "NTTE"
LD_PTR, RD_PTR, LD_DATA, START_FWD, START_INV, STATUS, RD_DATA, CYCLES = range(8)


def bench_cases():
    """(name, op, input): forward of a single one, of all 3328, of a random polynomial; inverse of the other random one."""
    p = polys()
    return [("single_one", "forward", p[1]), ("all_3328", "forward", p[2]), ("random_forward", "forward", p[3]),
            ("random_inverse", "inverse", p[4])]
