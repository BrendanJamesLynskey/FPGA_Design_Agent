"""Press classifier: clean presses of different lengths, with the long-press time and the length unit shrunk."""

LONG, TICK = 20, 4
HOLDS = [6, 25, 19, 20, 40, 8, 100, 3, 21, 12]          # clocks the debounced button is held
CLEAR_AT = 8                                              # before this press the short count is cleared over the shell


def trace(m):
    md = m.Model(LONG, TICK)
    x, h, la, ll, sc, lc, l0, l1, cap = [0], [0], [0], [0], [0], [0], [0], [0], []
    cap.append("Start: both counts are 0 and both LEDs are off.")
    for i, hold in enumerate(HOLDS, 1):
        note = ""
        if i == CLEAR_AT:
            md.write(m.SHORT_COUNT, 1)
            note = " (the short count was cleared by a shell write just before)"
        md.press(hold)
        last = md.read(m.LAST)
        x.append(i); h.append(hold); la.append(last & 0xFFFF); ll.append(last >> 16)
        sc.append(md.read(m.SHORT_COUNT)); lc.append(md.read(m.LONG_COUNT))
        st = md.read(m.STATUS)
        l0.append(st >> 1 & 1); l1.append(st >> 2 & 1)
        kind = "long" if ll[-1] else "short"
        cap.append(f"Press {i}: held {hold} clocks, with the long-press time at {LONG} clocks, so it is {kind}. The length reads {la[-1]} (units of {TICK} clocks); "
                   f"short count {sc[-1]}, long count {lc[-1]}{note}.")
    return {
        "stimulus": f"Clean presses are held for {', '.join(str(v) for v in HOLDS)} clocks in turn. The long-press time is {LONG} clocks and one length unit is {TICK} clocks (both shrunk). "
                    f"The short count is cleared over the shell before press {CLEAR_AT}.",
        "unit": "press", "x": x,
        "signals": [
            {"name": "held (clocks)", "kind": "wave", "v": h, "lo": 0},
            {"name": "LAST", "kind": "bus", "radix": "dec", "v": la},
            {"name": "LAST_LONG", "kind": "bit", "v": ll},
            {"name": "SHORT_COUNT", "kind": "bus", "radix": "dec", "v": sc},
            {"name": "LONG_COUNT", "kind": "bus", "radix": "dec", "v": lc},
            {"name": "LED[0]", "kind": "bit", "v": l0},
            {"name": "LED[1]", "kind": "bit", "v": l1},
        ],
        "captions": cap,
    }
