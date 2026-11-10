"""Decimal up/down counter: the model pressed repeatedly with different step switches, wrapping at both ends."""

START = 9985
PRESSES = [(0, "U"), (0, "U"), (1, "U"), (2, "U"), (3, "U"), (3, "U"), (3, "D"), (2, "D"), (1, "D"), (0, "D"),
           (0, "D"), (3, "D"), (3, "D"), (3, "D"), (2, "D"), (2, "U"), (3, "U"), (3, "U"), (3, "U"), (0, "U")]
SWITCH = ["00", "01", "10", "11"]


def trace(m):
    md = m.Model()
    md.write(m.COUNT, START)
    x, cnt, stp, wr, bcd, cap = [0], [md.read(m.COUNT)], [md.read(m.STEP)], [md.read(m.WRAPS)], [md.read(m.BCD)], []
    cap.append(f"Press 0: the count is set to {cnt[0]} over the shell, so the display shows {cnt[0]}. No wraps yet.")
    for i, (sw, d) in enumerate(PRESSES, 1):
        before, wb = md.read(m.COUNT), md.read(m.WRAPS)
        md.sw = sw
        md.press(up=d == "U", down=d == "D")
        x.append(i)
        cnt.append(md.read(m.COUNT)); stp.append(md.read(m.STEP)); wr.append(md.read(m.WRAPS)); bcd.append(md.read(m.BCD))
        word = "up" if d == "U" else "down"
        s = f"Press {i}: switches {SWITCH[sw]} give a step of {stp[-1]}; one press {word} takes {before} to {cnt[-1]}."
        if wr[-1] != wb:
            s += f" That passes the end of the range, so the wrap count becomes {wr[-1]}."
        cap.append(s)
    return {
        "stimulus": f"The count is set to {START}, then {len(PRESSES)} clean button presses are applied (the debounced "
                    f"button, so one press is one step), up or down, with the step switches changed between presses.",
        "unit": "press", "x": x,
        "signals": [
            {"name": "COUNT", "kind": "bus", "radix": "dec", "v": cnt},
            {"name": "STEP", "kind": "bus", "radix": "dec", "v": stp},
            {"name": "WRAPS", "kind": "bus", "radix": "dec", "v": wr},
            {"name": "BCD", "kind": "bus", "radix": "hex", "width": 16, "v": bcd},
        ],
        "captions": cap,
    }
