"""Static SVG figures from a capture: the eye heat map (log10 BER, contours at the decades, the chosen depth's contour heavier) and the horizontal bathtub.

Monochrome. A point with no errors is drawn at its 3/bits bound and carries a dot (it says "below this", not "zero"). A synthetic capture carries SYNTHETIC across the figure.
"""

from __future__ import annotations

import math
from html import escape
from typing import Any

from flow.eyescan import capture as C

W, H = 760, 520
INK, PAPER, MUTE = "#111", "#fff", "#666"


def _shade(z: float | None, zmin: float, zmax: float) -> str:
    """Grey for log10 BER: white at/below zmin (open), black at zmax (BER ~ 0.3)."""
    if z is None:
        return "#ddd"
    f = (z - zmin) / (zmax - zmin) if zmax > zmin else 0.0
    g = int(round(255 * (1 - min(1.0, max(0.0, f)) ** 0.8)))
    return f"#{g:02x}{g:02x}{g:02x}"


def contours(z: list[list[float | None]], level: float) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Marching squares on a grid of values (None = no data): segments in grid-index coordinates (x = column, y = row), cells with any missing corner skipped."""
    segs = []
    for r in range(len(z) - 1):
        for c in range(len(z[0]) - 1):
            q = [z[r][c], z[r][c + 1], z[r + 1][c + 1], z[r + 1][c]]
            if any(v is None for v in q):
                continue
            pts = [(c, r), (c + 1, r), (c + 1, r + 1), (c, r + 1)]
            edge = []
            for i in range(4):
                a, b = q[i], q[(i + 1) % 4]
                if (a - level) * (b - level) < 0:
                    t = (level - a) / (b - a)
                    (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % 4]
                    edge.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
            if len(edge) == 2:
                segs.append((edge[0], edge[1]))
            elif len(edge) == 4:
                segs.append((edge[0], edge[1])); segs.append((edge[2], edge[3]))
    return segs


def heatmap_svg(cap: dict[str, Any], depth: float = 1e-9, title: str | None = None) -> str:
    st = cap["settings"]
    s = C.surface(cap)
    hs, vs, z, bound = s["h"], s["v"], s["log10_ber"], s["zero_error_bound"]
    px0, py0, pw, ph = 70, 58, 640, 380
    cw, ch = pw / max(1, len(hs)), ph / max(1, len(vs))
    zmin, zmax = -12.0, -0.5
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="RX eye scan, log10 BER against horizontal and vertical offset" font-family="system-ui,sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="{PAPER}"/>']
    ttl = title or f"RX eye scan, {st['line_rate_gbps']} Gb/s, {st['equaliser']}, after the equaliser"
    o.append(f'<text x="{px0}" y="24" font-size="15" fill="{INK}">{escape(ttl)}</text>')
    sub = f"log10 BER per point (white: BER below 1e-12 or no errors seen; black: BER about 0.3). Bold line: BER {depth:g}. Dot: no errors seen, value is the 3/bits bound."
    o.append(f'<text x="{px0}" y="42" fill="{MUTE}">{escape(sub)}</text>')
    for r, v in enumerate(vs):
        for c, h in enumerate(hs):
            val = z[r][c]
            o.append(f'<rect x="{px0 + c * cw:.2f}" y="{py0 + (len(vs) - 1 - r) * ch:.2f}" width="{cw + 0.4:.2f}" height="{ch + 0.4:.2f}" fill="{_shade(val, zmin, zmax)}"/>')
            if bound[r][c]:
                o.append(f'<circle cx="{px0 + (c + 0.5) * cw:.1f}" cy="{py0 + (len(vs) - 1 - r + 0.5) * ch:.1f}" r="1.2" fill="{MUTE}"/>')

    def tx(x: float) -> float:
        return px0 + (x + 0.5) * cw

    def ty(y: float) -> float:
        return py0 + (len(vs) - 1 - y + 0.5) * ch
    for lev in range(-11, 0):
        heavy = abs(lev - math.log10(depth)) < 0.5
        for (a, b) in contours(z, float(lev)):
            o.append(f'<line x1="{tx(a[0]):.1f}" y1="{ty(a[1]):.1f}" x2="{tx(b[0]):.1f}" y2="{ty(b[1]):.1f}" stroke="{"#c00" if False else INK}" stroke-width="{2.2 if heavy else 0.6}" stroke-opacity="{1 if heavy else 0.55}"/>')
    o.append(f'<rect x="{px0}" y="{py0}" width="{pw}" height="{ph}" fill="none" stroke="{INK}"/>')
    for k in (-0.5, -0.25, 0, 0.25, 0.5):
        hx = k / st["ui_per_count"]
        if hs[0] <= hx <= hs[-1]:
            xx = px0 + (hx - hs[0]) / max(1, hs[-1] - hs[0]) * pw if hs[-1] > hs[0] else px0
            o.append(f'<line x1="{xx:.1f}" y1="{py0 + ph}" x2="{xx:.1f}" y2="{py0 + ph + 5}" stroke="{INK}"/><text x="{xx:.1f}" y="{py0 + ph + 18}" text-anchor="middle" fill="{INK}">{k:+.2f}</text>')
    o.append(f'<text x="{px0 + pw / 2}" y="{py0 + ph + 36}" text-anchor="middle" fill="{INK}">horizontal offset (UI)</text>')
    mv = st["mv_per_code"]
    for frac in (0, 0.25, 0.5, 0.75, 1):
        vv = vs[0] + frac * (vs[-1] - vs[0])
        yy = py0 + ph - frac * ph
        o.append(f'<line x1="{px0 - 5}" y1="{yy:.1f}" x2="{px0}" y2="{yy:.1f}" stroke="{INK}"/><text x="{px0 - 8}" y="{yy + 4:.1f}" text-anchor="end" fill="{INK}">{vv * mv:+.0f}</text>')
    o.append(f'<text transform="translate(16,{py0 + ph / 2}) rotate(-90)" text-anchor="middle" fill="{INK}">vertical offset (mV, nominal: {mv} mV per code)</text>')
    e = C.eye_at(cap, depth)
    wtxt = f"{e['width_ui']:.3f} UI (+/-{(e['width_ui_hi'] - e['width_ui_lo']) / 2:.3f} grid)" if e.get("width_ui") is not None else "none"
    htxt = f"{e['height_mv']:.0f} mV (+/-{(e['height_mv_hi'] - e['height_mv_lo']) / 2:.0f} grid)" if e.get("height_mv") is not None else "none"
    o.append(f'<text x="{px0}" y="{H - 14}" fill="{INK}">At BER {depth:g}: width {escape(wtxt)}, height {escape(htxt)}. Equaliser {st["equaliser"]}; {len(cap["points"])} points.</text>')
    if cap.get("synthetic"):
        o.append(f'<text x="{W / 2}" y="{py0 + ph / 2}" text-anchor="middle" font-size="64" fill="{INK}" fill-opacity="0.13" transform="rotate(-18 {W / 2} {py0 + ph / 2})">SYNTHETIC</text>')
    o.append("</svg>")
    return "\n".join(o)


def bathtub_svg(cap: dict[str, Any], depth: float = 1e-9, title: str | None = None) -> str:
    st = cap["settings"]
    b = C.bathtub_h(cap)
    px0, py0, pw, ph = 70, 50, 640, 320
    ys = []
    for r in b:
        if r["ber"] is None:
            continue
        ys.append(math.log10(r["ber"]) if r["err"] else math.log10(r["ber_ub"]))
    ymin, ymax = min(-12.0, math.floor(min(ys, default=-12))), 0.0
    xs = [r["ui"] for r in b]
    x0, x1 = (min(xs), max(xs)) if xs else (-0.5, 0.5)

    def X(u: float) -> float:
        return px0 + (u - x0) / (x1 - x0) * pw if x1 > x0 else px0

    def Y(l: float) -> float:
        return py0 + (ymax - l) / (ymax - ymin) * ph
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} 440" role="img" aria-label="Horizontal bathtub curve" font-family="system-ui,sans-serif" font-size="12"><rect width="{W}" height="440" fill="{PAPER}"/>']
    o.append(f'<text x="{px0}" y="24" font-size="15" fill="{INK}">{escape(title or "Horizontal bathtub, row nearest 0 mV, after the equaliser")}</text>')
    for l in range(int(ymin), 1):
        o.append(f'<line x1="{px0}" y1="{Y(l):.1f}" x2="{px0 + pw}" y2="{Y(l):.1f}" stroke="#ddd"/><text x="{px0 - 6}" y="{Y(l) + 4:.1f}" text-anchor="end" fill="{INK}">1e{l}</text>')
    pl = [(X(r["ui"]), Y(math.log10(r["ber"]) if r["err"] else math.log10(r["ber_ub"]))) for r in b if r["ber"] is not None]
    if pl:
        o.append(f'<polyline fill="none" stroke="{INK}" stroke-width="1.6" points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pl)}"/>')
    for r in b:
        if r["ber"] is None:
            continue
        x = X(r["ui"])
        if r["err"] == 0:
            y = Y(math.log10(r["ber_ub"]))
            o.append(f'<path d="M{x:.1f},{y:.1f} l-3,-6 l6,0 z" fill="{INK}"/>')            # triangle: "below this bound"
        else:
            o.append(f'<circle cx="{x:.1f}" cy="{Y(math.log10(r["ber"])):.1f}" r="2.4" fill="{INK}"/>')
    o.append(f'<line x1="{px0}" y1="{Y(math.log10(depth)):.1f}" x2="{px0 + pw}" y2="{Y(math.log10(depth)):.1f}" stroke="{INK}" stroke-dasharray="5 4"/>'
             f'<text x="{px0 + pw - 4}" y="{Y(math.log10(depth)) - 5:.1f}" text-anchor="end" fill="{INK}">depth {depth:g}</text>')
    o.append(f'<rect x="{px0}" y="{py0}" width="{pw}" height="{ph}" fill="none" stroke="{INK}"/>')
    for k in (-0.5, -0.25, 0, 0.25, 0.5):
        if x0 <= k <= x1:
            o.append(f'<text x="{X(k):.1f}" y="{py0 + ph + 18}" text-anchor="middle" fill="{INK}">{k:+.2f}</text>')
    o.append(f'<text x="{px0 + pw / 2}" y="{py0 + ph + 38}" text-anchor="middle" fill="{INK}">horizontal offset (UI)</text>')
    o.append(f'<text x="{px0}" y="{py0 + ph + 58}" fill="{MUTE}">Circle: BER from errors seen. Triangle: no errors seen, drawn at its 3/bits bound (the BER is below it). Equaliser {st["equaliser"]}.</text>')
    if cap.get("synthetic"):
        o.append(f'<text x="{W / 2}" y="{py0 + ph / 2}" text-anchor="middle" font-size="64" fill="{INK}" fill-opacity="0.13" transform="rotate(-12 {W / 2} {py0 + ph / 2})">SYNTHETIC</text>')
    o.append("</svg>")
    return "\n".join(o)
