"""PDM level meter: one step per block of microphone samples (block size shrunk), with a short hold and a fast decay."""

W = 64
HOLD, DECAY = 3, 2
ONES = [32, 33, 31, 34, 30, 40, 36, 32, 31, 32, 32, 32, 32, 32, 32, 32, 58, 34, 32, 32, 32, 32, 32, 32, 32, 32, 32, 32, 45, 32]


def trace(m):
    md = m.Model(W)
    md.write_ctrl(DECAY << 8 | HOLD)
    for o in ONES:
        md.block(o)
    x, on, lv, pk, led, cap = [], [], [], [], [], []
    for k in range(1, len(ONES) + 1):
        r = md.regs(k)
        h = md.history[k]
        x.append(k); on.append(r[m.ONES]); lv.append(r[m.LEVEL]); pk.append(r[m.PEAK]); led.append(h["led"])
        prev = md.history[k - 1]["peak"]
        if r[m.PEAK] > prev:
            note = f"New peak {r[m.PEAK]}, held for {HOLD} blocks."
        elif r[m.PEAK] == prev and h["hold"] < md.history[k - 1]["hold"]:
            note = f"Peak {r[m.PEAK]} is held (hold blocks left: {h['hold']})."
        elif r[m.PEAK] < prev:
            note = f"Peak falls by {prev - r[m.PEAK]} to {r[m.PEAK]}."
        else:
            note = f"Peak stays at {r[m.PEAK]}."
        cap.append(f"Block {k}: {r[m.ONES]} ones out of {W}, level {r[m.LEVEL]} (distance from {W // 2}). {bin(h['led']).count('1')} of 16 LEDs lit. {note}")
    return {
        "stimulus": f"Blocks of {W} microphone samples (shrunk) with the given number of ones: near {W // 2} for quiet, a loud burst of {max(ONES)} ones, "
                    f"then quiet again and a smaller burst of {ONES[28]}. Peak hold is {HOLD} blocks and decay is {DECAY} a block.",
        "unit": "block", "x": x,
        "signals": [
            {"name": "ONES", "kind": "wave", "v": on, "lo": 0, "hi": W},
            {"name": "LEVEL", "kind": "wave", "v": lv, "lo": 0, "hi": W // 2},
            {"name": "PEAK", "kind": "wave", "v": pk, "lo": 0, "hi": W // 2},
            {"name": "LED[15:0]", "kind": "bus", "radix": "bin", "width": 16, "v": led},
        ],
        "captions": cap,
    }
