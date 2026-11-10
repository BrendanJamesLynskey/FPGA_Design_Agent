"""NTT engine: the first coefficients of the model's random polynomial, its forward transform, and the inverse of that."""

SHOW = 16


def trace(m):
    p = m.polys()[3]
    f = m.ntt(p)
    back = m.intt(f)
    x, cap = list(range(SHOW)), []
    for i in x:
        cap.append(f"Coefficient {i}: input {p[i]}, forward transform {f[i]}, inverse of that {back[i]}" + (", back to the input." if back[i] == p[i] else "."))
    return {
        "stimulus": f"The random polynomial of {len(p)} coefficients (modulo {m.Q}) from the model, put through the forward transform and then the inverse; the first {SHOW} coefficients are shown.",
        "unit": "coefficient", "x": x,
        "signals": [
            {"name": "input", "kind": "bus", "radix": "dec", "width": 12, "v": [int(v) for v in p[:SHOW]]},
            {"name": "after forward NTT", "kind": "bus", "radix": "dec", "width": 12, "v": [int(v) for v in f[:SHOW]]},
            {"name": "after inverse NTT", "kind": "bus", "radix": "dec", "width": 12, "v": [int(v) for v in back[:SHOW]]},
        ],
        "captions": cap,
    }
