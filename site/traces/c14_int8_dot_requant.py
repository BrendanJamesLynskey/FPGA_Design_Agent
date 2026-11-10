"""Quantised layer unit: sixteen of the model's test cases, the saturating and exact-half ones among them."""

CASES = [9, 14, 19, 24, 25, 29, 0, 11, 304, 305, 306, 307, 308, 309, 310, 311]   # indices into m.vectors()


def trace(m):
    vs = m.vectors()
    x, acc, rr, relu, y, cap = [], [], [], [], [], []
    for i, k in enumerate(CASES):
        c = vs[k]
        a, yy = m.compute(**c)
        r = m.requant(a, c["mult"], c["shift"])
        x.append(i); acc.append(a); rr.append(r); relu.append(c["relu"]); y.append(yy)
        lim = ""
        if yy != r:
            lim = f" It is limited to {yy}."
        cap.append(f"Case {k}: eight products plus bias {c['bias']} give acc = {a}. Scaled by {c['mult']} / 2^{c['shift']} and rounded it is {r}; relu is {'on' if c['relu'] else 'off'}.{lim} y = {yy}.")
    return {
        "stimulus": f"{len(CASES)} cases picked from the model's fixed test set of {len(vs)}: random ones that fit the range, random ones that are limited, and the hand-made cases for limiting and for exact halves (cases {CASES[8]} to {CASES[-1]}).",
        "unit": "test case", "x": x,
        "signals": [
            {"name": "acc", "kind": "bus", "radix": "dec", "width": 32, "v": acc},
            {"name": "scaled (before limit)", "kind": "bus", "radix": "dec", "v": rr},
            {"name": "relu", "kind": "bit", "v": relu},
            {"name": "y", "kind": "bus", "radix": "dec", "width": 8, "v": y},
        ],
        "captions": cap,
    }
