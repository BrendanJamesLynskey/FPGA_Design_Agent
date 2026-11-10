"""Montgomery multiplier: the model's bench products, one operand pair per step."""


def trace(m):
    ref = {(c["a"], c["b"], c["n"]): c for c in m.reference_output()["cases"]}
    cs = m.bench_cases()
    x, A, B, N, R, K, cap = [], [], [], [], [], [], []
    for i, (a, b, n) in enumerate(cs):
        r = m.mont_mul(a, b, n)
        assert r == ref[(a, b, n)]["r"]
        k = ref[(a, b, n)]["clocks"]
        x.append(i); A.append(a); B.append(b); N.append(n); R.append(r); K.append(k)
        cap.append(f"Pair {i}: modulus of {n.bit_length()} bits. r = a x b x 2^-64 mod n = {r:#x}, which is below n. It takes {k} clocks.")
    return {
        "stimulus": f"{len(cs)} products from the model's bench set: 64-bit and 40-bit odd moduli, then the edge cases (zero, n minus one) and some prime moduli.",
        "unit": "operand pair", "x": x,
        "signals": [
            {"name": "a", "kind": "bus", "radix": "hex", "width": 64, "v": A},
            {"name": "b", "kind": "bus", "radix": "hex", "width": 64, "v": B},
            {"name": "n", "kind": "bus", "radix": "hex", "width": 64, "v": N},
            {"name": "r", "kind": "bus", "radix": "hex", "width": 64, "v": R},
            {"name": "clocks", "kind": "bus", "radix": "dec", "v": K},
        ],
        "captions": cap,
    }
