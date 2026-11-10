"""VGA colour bars: the model's colour at the first and last pixel of every bar, plus the first positions outside the picture."""

ROW = 100


def trace(m):
    pos = []
    for k in range(len(m.BARS)):
        pos += [(k * m.BAR_W, ROW), (k * m.BAR_W + m.BAR_W - 1, ROW)]
    pos += [(m.H_ACT, ROW), (0, m.V_ACT)]
    x, px, py, col, r, g, b, cap = [], [], [], [], [], [], [], []
    for i, (cx, cy) in enumerate(pos):
        c = m.colour_at(cx, cy)
        x.append(i); px.append(cx); py.append(cy); col.append(c)
        r.append(c >> 8 & 15); g.append(c >> 4 & 15); b.append(c & 15)
        if cx >= m.H_ACT or cy >= m.V_ACT:
            where = "right of the last column" if cx >= m.H_ACT else "below the last row"
            cap.append(f"Position ({cx}, {cy}) is {where}, outside the active area, so the colour is {c:03X}.")
        else:
            cap.append(f"Pixel ({cx}, {cy}) is in bar {cx // m.BAR_W} and its colour is {c:03X} (red {c >> 8 & 15}, green {c >> 4 & 15}, blue {c & 15}).")
    return {
        "stimulus": f"The model is asked for the colour at the first and last pixel of each of the {len(m.BARS)} bars of {m.BAR_W} pixels on row {ROW}, "
                    f"then for one pixel to the right of the {m.H_ACT} columns and one below the {m.V_ACT} rows.",
        "unit": "pixel", "x": x,
        "signals": [
            {"name": "X", "kind": "bus", "radix": "dec", "v": px},
            {"name": "Y", "kind": "bus", "radix": "dec", "v": py},
            {"name": "RGB", "kind": "bus", "radix": "hex", "width": 12, "v": col},
            {"name": "VGA_R", "kind": "bus", "radix": "hex", "width": 4, "v": r},
            {"name": "VGA_G", "kind": "bus", "radix": "hex", "width": 4, "v": g},
            {"name": "VGA_B", "kind": "bus", "radix": "hex", "width": 4, "v": b},
        ],
        "captions": cap,
    }
