"""Hough accumulator: the model's four-line picture, one step per direction showing the busiest distance in that direction."""


def trace(m):
    pts = m.points()
    acc = m.accumulate(pts)
    x, ang, cnt, rho, tot, cap = [], [], [], [], [], []
    for k in range(m.NT):
        row = [int(v) for v in acc[k]]
        peak = max(row); r = row.index(peak) - m.ROFF
        x.append(k); ang.append(k * 180 / m.NT); cnt.append(peak); rho.append(r); tot.append(sum(row))
        cap.append(f"Direction {k} ({k * 180 / m.NT:g} degrees): the busiest distance is {r}, where {peak} of the {len(pts)} points agree; {sum(row)} votes were cast in all.")
    return {
        "stimulus": f"The picture of {len(m.LINES)} straight lines on a 32 by 32 grid, which has {len(pts)} edge points. Each point votes in all {m.NT} directions.",
        "unit": "direction", "x": x,
        "signals": [
            {"name": "direction index", "kind": "bus", "radix": "dec", "v": x},
            {"name": "peak count", "kind": "wave", "lo": 0, "v": cnt},
            {"name": "peak distance", "kind": "bus", "radix": "dec", "v": rho},
            {"name": "votes in range", "kind": "bus", "radix": "dec", "v": tot},
        ],
        "captions": cap,
    }
