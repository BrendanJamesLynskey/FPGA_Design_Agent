"""Figures for the DSP-slice drawer of the expertise page (brief 185): inline SVG drawn from the committed measurements only.

    data(kind)   -> {"data": ..., "vals": {name: number}}   the plotted numbers (read from results/185_dsp_slices/data/<part>.json, nothing typed)
                                                            and the values the caption cites
    render(kind, fig, layout) -> SVG string               'wide' (side-by-side panels) or 'narrow' (stacked, for phones)

The figure data go into site/data/expertise.json, so every tick label and number on a figure is a data token that build.py's number check
can find. Sober black and white, text and lines use the site's CSS variables so dark mode follows. Fmax values are shown to the whole MHz.

Kinds: mul_depth (Fmax against latency of one multiply), dot_pareto (eight-term dot product: latency against Fmax), dsp_width (slices per width).
"""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "results" / "185_dsp_slices" / "data"
PARTS = [("a7", "Artix-7 xc7a100t (DSP48E1)"), ("k26", "Zynq UltraScale+ K26 (DSP48E2)")]
e = html.escape


def g(x: float) -> str:
    return f"{x:g}"


def _load(pk: str) -> list[dict]:
    return [p for p in json.loads((DATA / f"{pk}.json").read_text())["points"] if p.get("status") == "ok"]


def _mhz(p: dict) -> int:
    return int(round(p["fmax_mhz"]))


def _ticks(hi: float) -> list[int]:
    step = 200 if hi > 600 else 100
    return list(range(0, int(hi // step + 1) * step + 1, step))


def data(kind: str) -> dict:
    parts = []
    vals: dict = {}
    for pk, label in PARTS:
        pts = _load(pk)
        if kind == "mul_depth":
            sel = [p for p in pts if p["kind"] == "mul" and p["params"]["WA"] == 18 and p["params"]["RSTP"] == 0]
            dots = [{"latency": p["latency_clocks"], "fmax": _mhz(p), "regs": f'{p["params"]["NA"]}{p["params"]["NM"]}{p["params"]["NP"]}'} for p in sel]
            best = {}
            for d in dots:
                best[d["latency"]] = max(best.get(d["latency"], 0), d["fmax"])
            lines = [{"latency": k, "fmax": v} for k, v in sorted(best.items())]
            panel = {"key": pk, "label": label, "dots": dots, "line": lines, "xticks": [0, 1, 2, 3, 4]}
            panel["yticks"] = _ticks(max(d["fmax"] for d in dots))
            for k, v in best.items():
                vals[f"{pk}_best_{k}"] = v
        elif kind == "dot_pareto":
            sel = [p for p in pts if p["kind"] == "dot" and p["params"]["K"] == 8]
            dots = []
            for p in sel:
                name = "cascade" if p["params"]["STYLE"] == 0 else {1: "tree, register every level", 2: "tree, every 2 levels", 99: "tree, register at the end"}[p["params"]["TR"]]
                dots.append({"latency": p["latency_clocks"], "fmax": _mhz(p), "dsp": p["dsp"], "name": name})
                vals[f"{pk}_dot_{p['params']['STYLE']}_{p['params']['TR']}_f"] = _mhz(p)
                vals[f"{pk}_dot_{p['params']['STYLE']}_{p['params']['TR']}_l"] = p["latency_clocks"]
            panel = {"key": pk, "label": label, "dots": dots, "xticks": sorted({d["latency"] for d in dots})}
            panel["yticks"] = _ticks(max(d["fmax"] for d in dots))
        else:  # dsp_width
            rows = []
            for p in pts:
                if p["kind"] == "wide" and not (p["params"]["STYLE"] == 0 and p["params"]["NA"] == 2):
                    rows.append({"w": f'{p["params"]["WA"]} x {p["params"]["WB"]}', "style": p["params"]["STYLE"], "dsp": p["dsp"], "fmax": _mhz(p), "latency": p["latency_clocks"]})
            ws = []
            for r in rows:
                if r["w"] not in ws:
                    ws.append(r["w"])
            panel = {"key": pk, "label": label, "rows": rows, "widths": ws}
            for r in rows:
                vals[f"{pk}_{r['w'].replace(' x ', 'x')}_{r['style']}_dsp"] = r["dsp"]
                vals[f"{pk}_{r['w'].replace(' x ', 'x')}_{r['style']}_f"] = r["fmax"]
        parts.append(panel)
    return {"data": {"panels": parts}, "vals": vals}


# ---------------------------------------------------------------------------------------------------------------- drawing
INK = 'stroke="var(--ink)"'
TXT = 'fill="var(--ink-2)" font-size="11" font-family="var(--f-body)"'


def _scatter(panel: dict, x0: float, y0: float, w: float, h: float, xlab: str, labels: bool) -> str:
    xs, ys = panel["xticks"], panel["yticks"]
    xmin, xmax = min(xs), max(xs)
    ymax = max(ys)
    X = lambda v: x0 + 34 + (v - xmin) / max(1, (xmax - xmin)) * (w - 54)
    Y = lambda v: y0 + h - 28 - v / ymax * (h - 48)
    o = [f'<text x="{x0}" y="{y0 + 12}" {TXT} font-weight="600">{e(panel["label"])}</text>']
    for t in ys:
        o.append(f'<line x1="{x0 + 34}" x2="{x0 + w - 18}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="var(--rule)" stroke-width="1"/>'
                 f'<text x="{x0 + 30}" y="{Y(t) + 4:.1f}" text-anchor="end" {TXT}>{g(t)}</text>')
    for t in xs:
        o.append(f'<text x="{X(t):.1f}" y="{y0 + h - 12}" text-anchor="middle" {TXT}>{g(t)}</text>')
    o.append(f'<text x="{x0 + 34 + (w - 54) / 2:.1f}" y="{y0 + h + 2}" text-anchor="middle" {TXT}>{e(xlab)}</text>')
    if panel.get("line"):
        pts = " ".join(f'{X(p["latency"]):.1f},{Y(p["fmax"]):.1f}' for p in panel["line"])
        o.append(f'<polyline points="{pts}" fill="none" {INK} stroke-width="1.5"/>')
    placed: list[tuple[float, float]] = []
    for d in sorted(panel["dots"], key=lambda d: -d["fmax"]):
        cx, cy = X(d["latency"]), Y(d["fmax"])
        shape = d.get("name", "")
        if shape.startswith("tree"):
            o.append(f'<rect x="{cx - 4:.1f}" y="{cy - 4:.1f}" width="8" height="8" fill="var(--bg)" {INK} stroke-width="1.5"/>')
        else:
            o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="var(--ink)"/>')
        if labels and not any(abs(cx - px) < 34 and abs(cy - py) < 12 for px, py in placed):      # no two labels on top of each other
            placed.append((cx, cy))
            o.append(f'<text x="{cx + 7:.1f}" y="{cy + 4:.1f}" {TXT}>{g(d["fmax"])}</text>')
    return "".join(o)


def _bars(panel: dict, x0: float, y0: float, w: float, h: float) -> str:
    ws = panel["widths"]
    nmax = max(r["dsp"] for r in panel["rows"])
    nb = 3
    rowh = (h - 30) / len(ws)
    o = [f'<text x="{x0}" y="{y0 + 12}" {TXT} font-weight="600">{e(panel["label"])}</text>']
    fills = {0: "none", 1: "var(--ink)", 2: "var(--mute)"}
    for i, wd in enumerate(ws):
        yy = y0 + 22 + i * rowh
        o.append(f'<text x="{x0 + 46}" y="{yy + rowh / 2 + 3:.1f}" text-anchor="end" {TXT}>{e(wd)}</text>')
        for j, s in enumerate((0, 1, 2)):
            r = next(r for r in panel["rows"] if r["w"] == wd and r["style"] == s)
            bh = (rowh - 6) / nb
            bw = r["dsp"] / nmax * (w - 110)
            o.append(f'<rect x="{x0 + 52}" y="{yy + j * bh:.1f}" width="{bw:.1f}" height="{bh - 1.5:.1f}" fill="{fills[s]}" {INK} stroke-width="1"/>'
                     f'<text x="{x0 + 56 + bw:.1f}" y="{yy + j * bh + bh - 3:.1f}" {TXT}>{r["dsp"]}</text>')
    return "".join(o)


def render(kind: str, fig: dict, layout: str) -> str:
    panels = fig["data"]["panels"]
    if layout == "wide":
        W, pw, ph = 640, 300, 240 if kind != "dsp_width" else 330
        place = [(10 + i * (pw + 20), 6) for i in range(len(panels))]
        H = ph + 22
    else:
        W, pw, ph = 360, 340, 220 if kind != "dsp_width" else 330
        place = [(10, 6 + i * (ph + 20)) for i in range(len(panels))]
        H = len(panels) * (ph + 20) + 8
    body = []
    for pn, (x0, y0) in zip(panels, place):
        if kind == "dsp_width":
            body.append(_bars(pn, x0, y0, pw, ph))
        else:
            body.append(_scatter(pn, x0, y0, pw, ph, "latency, register stages from inputs to output", kind == "dot_pareto" or layout == "wide"))
    if kind == "dsp_width":
        H += 44
        body.append(f'<text x="10" y="{H - 34}" {TXT}>bars in each group, top to bottom: open = inferred by the tool;</text>'
                    f'<text x="10" y="{H - 21}" {TXT}>black = hand-written cascade;</text>'
                    f'<text x="10" y="{H - 8}" {TXT}>grey = partial products summed in the fabric</text>')
    return (f'<svg viewBox="0 0 {W} {H:g}" role="img" aria-label="{e(fig["title"])}" class="dspfig" style="width:100%;height:auto;max-width:{W}px">'
            f'<title>{e(fig["title"])}</title>{"".join(body)}</svg>')
