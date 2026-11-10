"""Median filter: windows presented on a pattern of clocks, each median one clock (the model's LAT) later."""

PICK = [0, 113, 160, 106, 173, 231, 112, 161, 107, 262]   # indices into the model's test windows: random, single outliers, a half split, runs of 0, 17 and 255, equal pixels
PATTERN = "1101100111001010"                                # a 1 presents the next window on that clock, as the shell's MASK does
N = 18


def trace(m):
    ws = m.windows()
    pick = [ws[i] for i in PICK]
    inv, inw, outv, outm, cap, wins, sorts = [], [], [], [], [], [], []
    presented = []          # (clock, window)
    k = 0
    for t in range(N):
        pv = t < len(PATTERN) and PATTERN[t] == "1" and k < len(pick)
        if pv:
            presented.append((t, pick[k])); k += 1
        inv.append(1 if pv else 0)
        inw.append(" ".join(str(p) for p in presented[-1][1]) if pv else "")
        res = [w for (c, w) in presented if c + m.LAT == t]
        outv.append(1 if res else 0)
        outm.append(str(m.median(res[0])) if res else "")
        wins.append(presented[-1][1] if pv else None)
        sorts.append(sorted(res[0]) if res else None)
        words = []
        if pv:
            words.append(f"a window is presented ({inw[-1]})")
        if res:
            words.append(f"the median of the window from clock {t - m.LAT} comes out: {m.median(res[0])}")
        cap.append(f"Clock {t}: " + ("; ".join(words) if words else "nothing presented, no result") + ".")
    return {
        "stimulus": f"{len(pick)} of the model's test windows presented on the clocks where the pattern {PATTERN} has a 1; "
                    f"latency {m.LAT} clock.",
        "unit": "clock", "x": list(range(N)),
        "signals": [
            {"name": "window valid", "kind": "bit", "v": inv},
            {"name": "window", "kind": "text", "v": inw},
            {"name": "result valid", "kind": "bit", "v": outv},
            {"name": "median", "kind": "text", "v": outm},
        ],
        "captions": cap,
        "hero": {"in": wins, "sorted": sorts, "lat": m.LAT},
    }
