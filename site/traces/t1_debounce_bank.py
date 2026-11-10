"""Debounce bank: the model is given switch patterns that have been steady longer than the debounce time."""

# ("sw", pattern) = switches settle at this pattern; ("fall", mask) = enable falling edges; ("clear", mask) = clear flags
ACTIONS = [("sw", 0x0005), ("sw", 0x0007), ("clear", 0x0007), ("fall", 0x0004), ("sw", 0x0003), ("sw", 0x0007),
           ("sw", 0x0004), ("clear", 0x0004), ("sw", 0x8004), ("sw", 0x8000), ("sw", 0x8004), ("sw", 0x0000),
           ("clear", 0xFFFF), ("sw", 0x0001)]


def trace(m):
    md = m.Model()
    x, lv, ed, c0, c2, cap = [0], [md.read(m.LEVEL)], [md.read(m.EDGES)], [md.read(m.COUNT0) & 0xFF], [md.read(m.COUNT0) >> 16 & 0xFF], []
    cap.append("Start: all clean levels 0, no edge flags, rising edges enabled, falling edges not.")
    for i, (kind, v) in enumerate(ACTIONS, 1):
        a, b = md.read(m.LEVEL), md.read(m.EDGES)
        if kind == "sw":
            md.settle(v)
            ch = md.read(m.LEVEL) ^ a
            ks = [str(k) for k in range(16) if ch >> k & 1]
            names = (ks[0] if len(ks) == 1 else ", ".join(ks[:-1]) + " and " + ks[-1]) if ks else ""
            s = f"Step {i}: switches held at {v:016b} long enough; switch{'es' if len(ks) > 1 else ''} {names} {'change their' if len(ks) > 1 else 'changes its'} clean level." if ks else f"Step {i}: switches held at {v:016b}; no clean level changes."
        elif kind == "fall":
            md.write(m.FALL_EN, v)
            s = f"Step {i}: falling edges are enabled for the switches in mask {md.read(m.FALL_EN):04X}."
        else:
            md.write(m.EDGES, v)
            s = f"Step {i}: writing ones with mask {v:04X} clears those edge flags, leaving {md.read(m.EDGES):04X}."
        if kind == "sw":
            new = md.read(m.EDGES) & ~b
            if new:
                s += f" New edge flags set: {new:04X}."
        x.append(i); lv.append(md.read(m.LEVEL)); ed.append(md.read(m.EDGES))
        c0.append(md.read(m.COUNT0) & 0xFF); c2.append(md.read(m.COUNT0) >> 16 & 0xFF)
        cap.append(s)
    return {
        "stimulus": "Switch patterns are applied after each has been steady for longer than the debounce time (glitches shorter "
                    "than that never reach the model). Between them the edge flags are cleared and falling edges are enabled for one switch.",
        "unit": "step", "x": x,
        "signals": [
            {"name": "LEVEL", "kind": "bus", "radix": "bin", "width": 16, "v": lv},
            {"name": "EDGES", "kind": "bus", "radix": "bin", "width": 16, "v": ed},
            {"name": "COUNT[0]", "kind": "bus", "radix": "dec", "v": c0},
            {"name": "COUNT[2]", "kind": "bus", "radix": "dec", "v": c2},
        ],
        "captions": cap,
    }
