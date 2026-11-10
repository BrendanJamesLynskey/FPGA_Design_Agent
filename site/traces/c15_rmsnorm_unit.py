"""RMS norm: the 16 lanes of one of the model's input vectors, input against output."""

CASE = 530


def trace(m):
    xs = m.inputs()[CASE]
    ys = m.reference_output()["y"][CASE]
    ms = sum(v * v for v in xs) / m.N / 256 ** 2
    x, cap = [], []
    for i in range(m.N):
        x.append(i)
        cap.append(f"Lane {i}: input {xs[i]} ({xs[i] / 256:.2f} in real units) becomes {ys[i]} ({ys[i] / 256:.2f}).")
    return {
        "stimulus": f"Input vector number {CASE} of the model's set: {m.N} numbers, value times 256. The mean of the squares of the real values is {ms:.2f}, so every lane is divided by its square root.",
        "unit": "lane", "x": x,
        "signals": [
            {"name": "input", "kind": "wave", "lo": -32768, "hi": 32767, "v": [int(v) for v in xs]},
            {"name": "output", "kind": "wave", "lo": -32768, "hi": 32767, "v": [int(v) for v in ys]},
        ],
        "captions": cap,
    }
