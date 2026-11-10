"""Corner finder: the model's course picture, one step per corner it reports, with the corner response there."""


def trace(m):
    img = m.scene()
    R = m.response_map(img)
    cs = m.corners(img)
    x, px, py, resp, cap = [], [], [], [], []
    for i, (cx, cy) in enumerate(cs):
        r = int(R[cy + 3, cx + 3])
        x.append(i); px.append(int(cx)); py.append(int(cy)); resp.append(r)
        cap.append(f"Corner {i}: at x = {cx}, y = {cy}, where the corner response is {r}, above the threshold of {m.THRESH} and the largest in its neighbourhood.")
    return {
        "stimulus": f"The {m.W} by {m.H} picture with {len(m.BOXES)} bright rectangles on a dark background. The model computes the corner response everywhere and keeps the local peaks above the threshold.",
        "unit": "corner", "x": x,
        "signals": [
            {"name": "SEL (list place)", "kind": "bus", "radix": "dec", "v": x},
            {"name": "corner x", "kind": "bus", "radix": "dec", "v": px},
            {"name": "corner y", "kind": "bus", "radix": "dec", "v": py},
            {"name": "response", "kind": "bus", "radix": "dec", "v": resp},
        ],
        "captions": cap,
    }
