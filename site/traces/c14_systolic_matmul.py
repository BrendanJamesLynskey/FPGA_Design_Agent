"""4 x 4 row multiplier: rows accepted on consecutive clocks, each result row the model's LATENCY clocks later."""

NROWS = 10
N = 19


def trace(m):
    W = m.weights()
    rs = m.rows()[:NROWS]
    C = m.matmul(rs, W)
    L = m.LATENCY
    inv, inr, outv, outr, cap, hin, hout = [], [], [], [], [], [], []
    for t in range(N):
        i = t if t < NROWS else None
        o = t - L if 0 <= t - L < NROWS else None
        inv.append(1 if i is not None else 0)
        inr.append(" ".join(str(x) for x in rs[i]) if i is not None else "")
        outv.append(1 if o is not None else 0)
        outr.append(" ".join(str(x) for x in C[o]) if o is not None else "")
        hin.append(i); hout.append(o)
        words = []
        if i is not None:
            words.append(f"row {i} ({inr[-1]}) goes in")
        if o is not None:
            words.append(f"result row {o} comes out ({outr[-1]})")
        cap.append(f"Clock {t}: " + ("; ".join(words) if words else "pipeline empty") + ".")
    return {
        "stimulus": f"The model's first {NROWS} test rows of four signed 8-bit numbers, one row a clock, times its fixed "
                    f"4 x 4 weight matrix; latency {L} clocks.",
        "unit": "clock", "x": list(range(N)),
        "signals": [
            {"name": "row valid", "kind": "bit", "v": inv},
            {"name": "row in", "kind": "text", "v": inr},
            {"name": "out valid", "kind": "bit", "v": outv},
            {"name": "result row", "kind": "text", "v": outr},
        ],
        "captions": cap,
        "hero": {"W": W, "rows": rs, "C": C, "lat": L, "in": hin, "out": hout},
    }
