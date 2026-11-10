"""Softmax: eight lanes of two of the model's score sets (a ramp of scores, and a random set)."""

CASES = [4, 100]


def trace(m):
    xs_all, ps_all = m.inputs(), m.reference_output()["p"]
    x, cs, xin, pout, cap = [], [], [], [], []
    i = 0
    for c in CASES:
        xs, ps = xs_all[c], ps_all[c]
        for lane in range(m.N):
            x.append(i); i += 1
            cs.append(c); xin.append(int(xs[lane])); pout.append(int(ps[lane]))
            cap.append(f"Set {c}, lane {lane}: score {xs[lane]} ({xs[lane] / 256:.2f} in real units) gets probability {ps[lane]} out of 32768 ({ps[lane] * 100 / 32768:.1f} per cent).")
    return {
        "stimulus": f"Two score sets of {m.N} lanes from the model: set {CASES[0]} and set {CASES[1]}. Each probability is the exponential of the lane's score divided by the sum over the lanes.",
        "unit": "lane", "x": x,
        "signals": [
            {"name": "set", "kind": "bus", "radix": "dec", "v": cs},
            {"name": "score x256", "kind": "wave", "v": xin},
            {"name": "probability x32768", "kind": "wave", "lo": 0, "hi": 32768, "v": pout},
        ],
        "captions": cap,
    }
