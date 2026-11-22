"""Figures for the signal-integrity drawer of the expertise page (brief 164): inline SVG drawn from committed result files only.

    data(kind)   -> {"data": ..., "vals": {name: number}}   the plotted numbers (read from results/155_offchip, results/162_kr260_si and
                                                            results/164_si_expertise; nothing typed) and the values the caption cites
    render(kind, fig, layout) -> SVG string               'wide' (a 640-unit drawing) or 'narrow' (a 360-unit drawing for phones)

The figure data go into site/data/expertise.json, so every tick label and number on a figure is a data token that build.py's number
check can find. Sober black and white: ink lines with different dashes, hatched forbidden regions, no colour but the site's warning tone for the
data-sheet limit; text and lines use the site's CSS variables, so dark mode follows.

Kinds: waveforms (receiver voltage against series R), sweep (pass map), kr260 (two answers per port), rout (output resistance against DRIVE).
"""
from __future__ import annotations

import csv
import html
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R155, R162, R164 = ROOT / "results/155_offchip", ROOT / "results/162_kr260_si", ROOT / "results/164_si_expertise"
e = html.escape


def _rows(p: Path) -> list[dict]:
    with p.open() as f:
        return list(csv.DictReader(f))


def g(x: float) -> str:
    return f"{x:g}"


# ---------------------------------------------------------------------------------------------------------------- data

def _waveforms() -> dict:
    rows = _rows(R164 / "waveforms_series_r.csv")
    panels: dict[str, dict] = {}
    for r in rows:
        p = panels.setdefault(r["panel"], {"label": r["panel"], "standard": r["standard"], "bank": r["bank"], "vcco_v": float(r["vcco_v"]),
                                           "limit_over_v": float(r["limit_over_v"]), "limit_under_v": float(r["limit_under_v"]),
                                           "vih_v": float(r["vih_v"]), "vil_v": float(r["vil_v"]), "drive_ma": int(r["drive_ma"]), "slew": r["slew"],
                                           "length_in": float(r["length_in"]), "c_pf": float(r["c_pf"]), "z0_ohm": float(r["z0_ohm"]),
                                           "model": r["model"], "ibis_file": r["ibis_file"], "file_rev": r["file_rev"], "series": {}})
        s = p["series"].setdefault(int(r["series_ohm"]), {"ohm": int(r["series_ohm"]), "rise": [], "fall": []})
        s["rise" if r["edge"] == "rise" else "fall"].append([float(r["t_ns"]), float(r["v_rx_v"])])
    out = list(panels.values())
    vals = {}
    for p in out:
        p["series"] = [p["series"][k] for k in sorted(p["series"])]
        k = "hr33" if p["standard"] == "LVCMOS33" else "hp18"
        for s in p["series"]:
            vs = [v for e_ in ("rise", "fall") for _, v in s[e_]]
            vals[f"{k}_over_{s['ohm']}"] = round(max(vs) - p["vcco_v"], 2)
            vals[f"{k}_under_{s['ohm']}"] = round(-min(vs), 2)
        lo = min(min(v for _, v in s[e_]) for s in p["series"] for e_ in ("rise", "fall"))
        hi = max(max(v for _, v in s[e_]) for s in p["series"] for e_ in ("rise", "fall"))
        p["y_lo"] = float(int(min(p["limit_under_v"] - 0.3, lo - 0.1) * 2 - 1) / 2) if lo < 0 else p["limit_under_v"] - 0.3
        p["y_hi"] = max(p["limit_over_v"] + 0.3, hi + 0.1)
        p["yticks"] = [0.0, p["vcco_v"]]
        p["xticks"] = [0, 4, 8]
    vals.update(length_in=out[0]["length_in"], c_pf=out[0]["c_pf"], z0_ohm=out[0]["z0_ohm"], drive_ma=out[0]["drive_ma"], limit=0.2)
    return {"data": {"panels": out}, "vals": vals}


def _sweep() -> dict:
    rows = _rows(R162 / "drive_slew_sweep.csv")
    cells: dict = defaultdict(lambda: [0, 0])
    for r in rows:
        k = (r["bank"], r["standard"], int(r["length_in"]), int(r["series_ohm"]))
        cells[k][1] += 1
        cells[k][0] += r["pass"] == "True"
    panels = []
    vals = {}
    for bank, std, key in (("7-series HR", "LVCMOS33", "hr33"), ("7-series HR", "LVCMOS25", "hr25"), ("UltraScale+ HP", "LVCMOS18", "hp18")):
        lens = sorted({k[2] for k in cells if k[:2] == (bank, std)})
        rs = sorted({k[3] for k in cells if k[:2] == (bank, std)})
        panels.append({"bank": bank, "standard": std, "lengths": lens, "series": rs,
                       "cells": [[cells[(bank, std, ln, r)] for ln in lens] for r in rs]})
        for ln in lens:
            for r in (22, 33, 47):
                p, t = cells[(bank, std, ln, r)]
                vals[f"{key}_{r}_{ln}"] = p
                vals[f"{key}_total"] = t
    vals.update(n_runs=len(rows), z0_ohm=50, c_pf=5)
    return {"data": {"panels": panels, "z0_ohm": 50, "c_pf": 5, "n_runs": len(rows)}, "vals": vals}


def _kr260() -> dict:
    d = json.loads((R164 / "kr260_two_answers.json").read_text())
    wf: dict = defaultdict(lambda: {"rise": [], "fall": []})
    for r in _rows(R164 / "kr260_waveforms.csv"):
        wf[(r["assumption"], r["group"], r["answer"])]["rise" if r["edge"] == "rise" else "fall"].append([float(r["t_ns"]), float(r["v_rx_v"])])
    ports = []
    for p in d["ports"]:
        q = dict(p)
        q["waves"] = {a: wf[(p["assumption"], p["group"], a)] for a in ("xdc", "as_built", "optimal")}
        q.pop("dci", None)
        ports.append(q)
    vals = {"limit": d["limit_v"], "xdc_drive": d["xdc_setting"]["drive"]}
    for p in ports:
        if p["assumption"] == "measured":
            k = p["port"].lower()
            vals[f"{k}_len"] = p["length_in"]
            vals[f"{k}_ui"] = p["ui_ns"]
            for a, an in p["answers"].items():
                vals[f"{k}_{a}_t"] = max(an["t_over_ns"], an["t_under_ns"])
                vals[f"{k}_{a}_peak"] = max(an["worst_over_v"], an["worst_under_v"])
                vals[f"{k}_{a}_r"] = an["series_ohm"]
                vals[f"{k}_{a}_drive"] = an["drive"]
                vals[f"{k}_{a}_edge"] = an["rx_rise_2080_ns_weak"]
                vals[f"{k}_{a}_max"] = an["max_rise_ns"]
        else:
            k = p["port"].lower()
            vals[f"{k}_assumed_len"] = p["length_in"]
            vals[f"{k}_assumed_t"] = max(p["answers"]["xdc"]["t_over_ns"], p["answers"]["xdc"]["t_under_ns"])
    return {"data": {"ports": ports, "limit_v": d["limit_v"], "note": d["note"], "xdc_setting": d["xdc_setting"]}, "vals": vals}


def _rout() -> dict:
    rows = _rows(R155 / "r_out.csv")
    panels = []
    for bank, std, label in (("7-series HR", "LVCMOS33", "LVCMOS33, 7-series HR"), ("7-series HR", "LVCMOS25", "LVCMOS25, 7-series HR"),
                             ("UltraScale+ HP", "LVCMOS18", "LVCMOS18, UltraScale+ HP")):
        by: dict = defaultdict(dict)
        for r in rows:
            if (r["bank"], r["standard"]) == (bank, std):
                by[(int(r["drive_ma"]), r["slew"])][r["corner"]] = float(r["r_pu_ohm_into_z0"])
        drives = sorted({k[0] for k in by})
        slews = [s for s in ("SLOW", "MEDIUM", "FAST") if any(k[1] == s for k in by)]
        panels.append({"label": label, "standard": std, "bank": bank, "drives": drives, "slews": slews,
                       "points": [{"slew": s, "drive": d_, "typ": by[(d_, s)]["typ"], "weak": by[(d_, s)]["min"], "strong": by[(d_, s)]["max"]}
                                  for s in slews for d_ in drives if (d_, s) in by]})
    vals = {}
    p0 = panels[0]["points"]
    vals["hr33_r_4"] = [x for x in p0 if x["drive"] == 4 and x["slew"] == "FAST"][0]["typ"]
    vals["hr33_r_16"] = [x for x in p0 if x["drive"] == 16 and x["slew"] == "FAST"][0]["typ"]
    vals.update(z0_ohm=50, target_ohm=28)
    return {"data": {"panels": panels, "z0_ohm": 50, "series_ohm": 22, "target_ohm": 28}, "vals": vals}


def data(kind: str) -> dict:
    return {"waveforms": _waveforms, "sweep": _sweep, "kr260": _kr260, "rout": _rout}[kind]()


# ---------------------------------------------------------------------------------------------------------------- drawing

DASH = {0: "", 22: "7 3", 33: "2 3", 47: "9 3 2 3"}           # series R -> stroke-dasharray, so the key reads in black and white
WIDTH = {0: 2.0, 22: 1.6, 33: 2.0, 47: 1.6}
ANS_DASH = {"xdc": "", "as_built": "7 3", "optimal": "2 3"}
ANS_NAME = {"xdc": "as set in the XDC", "as_built": "best as built", "optimal": "optimal"}


class Fig:
    """A tiny SVG canvas with a plot area; ids are made unique per figure and layout."""

    def __init__(self, uid: str, w: int, h: int, title: str, desc: str):
        self.uid, self.w, self.h = uid, w, h
        self.parts: list[str] = []
        self.title, self.desc = title, desc

    def add(self, s: str):
        self.parts.append(s)

    def text(self, x, y, s, anchor="start", cls=""):
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}"{(" class=%s" % chr(34) + cls + chr(34)) if cls else ""}>{e(str(s))}</text>')

    def svg(self, extra_defs: str = "") -> str:
        return (f'<svg viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="{self.uid}t {self.uid}d">'
                f'<title id="{self.uid}t">{e(self.title)}</title><desc id="{self.uid}d">{e(self.desc)}</desc>'
                f'<defs>{extra_defs}<pattern id="{self.uid}h" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
                f'<line x1="0" y1="0" x2="0" y2="5" class="hl"/></pattern></defs>' + "".join(self.parts) + "</svg>")


def wrap_text(f: Fig, x: float, y: float, text: str, layout: str, lh: float = 15) -> float:
    """Add ``text`` as lines that fit the drawing (about 6.6 units a character wide, 8.4 narrow); returns the y below the last line."""
    per = int((f.w - x - 6) / (6.6 if layout == "wide" else 8.4))
    line = ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > per:
            f.text(x, y, line)
            y += lh
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        f.text(x, y, line)
        y += lh
    return y


def _path(pts, sx, sy, x0=0.0) -> str:
    return "M" + " L".join(f"{sx(t + x0):.1f} {sy(v):.1f}" for t, v in pts)


def _wave_panel(f: Fig, p: dict, ox: float, oy: float, w: float, h: float, layout: str, lines: list[tuple[str, str, float, list, list]]):
    """One waveform plot. lines: (label, dash, width, rise points, fall points). The rising edge is drawn left, the falling edge right."""
    pad_l, pad_b, pad_t = (34, 32, 6) if layout == "wide" else (40, 36, 6)
    x_lo, x_hi, y_lo, y_hi = -0.5, 24.5, p["y_lo"], p["y_hi"]
    pw, ph = w - pad_l - 4, h - pad_b - pad_t
    sx = lambda t: ox + pad_l + (t - x_lo) / (x_hi - x_lo) * pw
    sy = lambda v: oy + pad_t + (y_hi - v) / (y_hi - y_lo) * ph
    # forbidden regions: beyond the data-sheet limit
    f.add(f'<rect x="{sx(x_lo):.1f}" y="{sy(y_hi):.1f}" width="{pw:.1f}" height="{sy(p["limit_over_v"]) - sy(y_hi):.1f}" fill="url(#{f.uid}h)"/>')
    f.add(f'<rect x="{sx(x_lo):.1f}" y="{sy(p["limit_under_v"]):.1f}" width="{pw:.1f}" height="{sy(y_lo) - sy(p["limit_under_v"]):.1f}" fill="url(#{f.uid}h)"/>')
    for v in (p["limit_over_v"], p["limit_under_v"]):
        f.add(f'<line x1="{sx(x_lo):.1f}" y1="{sy(v):.1f}" x2="{sx(x_hi):.1f}" y2="{sy(v):.1f}" class="warn" stroke-width="1.2"/>')
    for v in (0.0, p["vcco_v"]):
        f.add(f'<line x1="{sx(x_lo):.1f}" y1="{sy(v):.1f}" x2="{sx(x_hi):.1f}" y2="{sy(v):.1f}" class="rule"/>')
    f.add(f'<line x1="{sx(12):.1f}" y1="{sy(y_hi):.1f}" x2="{sx(12):.1f}" y2="{sy(y_lo):.1f}" class="rule" stroke-dasharray="2 3"/>')
    f.add(f'<rect x="{ox + pad_l:.1f}" y="{oy + pad_t:.1f}" width="{pw:.1f}" height="{ph:.1f}" class="ink" stroke-width="1"/>')
    for v in p["yticks"]:
        f.text(ox + pad_l - 4, sy(v) + 4, g(v), "end")
    f.text(ox + pad_l - 4, sy(p["limit_over_v"]) - 3, g(p["limit_over_v"]), "end", "wn")
    f.text(ox + pad_l - 4, sy(p["limit_under_v"]) + 11, g(p["limit_under_v"]), "end", "wn")
    for half, name in ((0, "rising edge"), (12, "falling edge")):
        for t in p["xticks"]:
            f.add(f'<line x1="{sx(half + t):.1f}" y1="{sy(y_lo):.1f}" x2="{sx(half + t):.1f}" y2="{sy(y_lo) + 3:.1f}" class="ink"/>')
            f.text(sx(half + t), sy(y_lo) + 14, g(t), "middle")
        f.text(sx(half + 6), sy(y_lo) + (26 if layout == "wide" else 30), name + (", ns from the edge" if layout == "wide" else ", ns"), "middle")
    for _lab, dash, width, rise, fall in lines:
        for pts, x0 in ((rise, 0.0), (fall, 12.0)):
            f.add(f'<path d="{_path(pts, sx, sy, x0)}" class="ink" stroke-width="{width}"' + (f' stroke-dasharray="{dash}"' if dash else "") + ' stroke-linejoin="round"/>')
    return sx, sy


def _key(f: Fig, x: float, y: float, items: list[tuple[str, str, float]], cols: int, cw: float):
    for i, (lab, dash, width) in enumerate(items):
        cx, cy = x + (i % cols) * cw, y + (i // cols) * 16
        f.add(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx + 22:.1f}" y2="{cy:.1f}" class="ink" stroke-width="{width}"' + (f' stroke-dasharray="{dash}"' if dash else "") + "/>")
        f.text(cx + 27, cy + 4, lab)


def waveforms(fig: dict, layout: str) -> str:
    P = fig["data"]["panels"]
    wide = layout == "wide"
    w, ph = (640, 250) if wide else (360, 250)
    n = len(P)
    h = (ph + 66) if wide else n * (ph + 6) + 96
    f = Fig(f"wf{layout}", w, h, "Receiver waveforms with 0, 22, 33 and 47 ohm in series",
            "Rising and falling edges at the receiver of a 50 ohm line, one panel per I/O standard, with the data sheet overshoot and undershoot limits drawn as lines.")
    for i, p in enumerate(P):
        ox, oy = (i * (w / n), 18) if wide else (0, 18 + i * (ph + 6))
        f.text(ox + 36, oy - 6, f'{p["standard"]} DRIVE {p["drive_ma"]} {p["slew"]}, {g(p["length_in"])} in', "start")
        lines = [(f'{s["ohm"]}', DASH[s["ohm"]], WIDTH[s["ohm"]], s["rise"], s["fall"]) for s in p["series"]]
        _wave_panel(f, p, ox, oy, w / n if wide else w, ph, layout, lines)
    ky = ph + 42 if wide else n * (ph + 6) + 24
    key = [(f'{s["ohm"]} ohm in series', DASH[s["ohm"]], WIDTH[s["ohm"]]) for s in P[0]["series"]]
    _key(f, 40 if wide else 8, ky, key, 4 if wide else 2, 150 if wide else 160)
    ky2 = ky + (22 if wide else 38)
    f.add(f'<rect x="{40 if wide else 8}" y="{ky2:.1f}" width="22" height="9" fill="url(#{f.uid}h)" class="ink" stroke-width="0.6"/>')
    wrap_text(f, 68 if wide else 36, ky2 + 8, f'beyond the data sheet limit (VCCO + {g(P[0]["limit_over_v"] - P[0]["vcco_v"])} V, GND - {g(-P[0]["limit_under_v"])} V)', layout)
    return f.svg()


def sweep(fig: dict, layout: str) -> str:
    P = fig["data"]["panels"]
    wide = layout == "wide"
    cw, ch = (58, 26) if wide else (54, 26)
    lm, tm = 52, 40
    pw = lm + cw * len(P[0]["lengths"]) + 12
    ph = tm + ch * len(P[0]["series"]) + 40
    w = pw * len(P) if wide else max(pw, 300)
    h = ph if wide else ph * len(P)
    f = Fig(f"sw{layout}", int(w), int(h), "Where a series resistor passes: resistor value against line length",
            "For three I/O standards, a grid of series resistor value against line length; each cell shows how many DRIVE and SLEW combinations pass every limit.")
    for i, p in enumerate(P):
        ox, oy = (i * pw, 0) if wide else (0, i * ph)
        f.text(ox + 4, oy + 16, f'{p["standard"]}, {p["bank"]}')
        f.text(ox + lm, oy + 33, "line length, in")
        for c, ln in enumerate(p["lengths"]):
            f.text(ox + lm + c * cw + cw / 2, oy + tm - 2, g(ln), "middle")
        for r, rs in enumerate(p["series"]):
            y = oy + tm + r * ch
            f.text(ox + lm - 6, y + ch / 2 + 4, g(rs), "end")
            for c, ln in enumerate(p["lengths"]):
                ok, tot = p["cells"][r][c]
                frac = ok / tot
                x = ox + lm + c * cw
                f.add(f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" class="cell" style="fill-opacity:{0.08 + 0.8 * frac:.2f}"/>')
                f.add(f'<text x="{x + cw / 2}" y="{y + ch / 2 + 4}" text-anchor="middle" class="{"on" if frac > 0.5 else ""}">{ok}/{tot}</text>')
        r22 = p["series"].index(22)
        f.add(f'<rect x="{ox + lm - 1}" y="{oy + tm + r22 * ch - 1}" width="{cw * len(p["lengths"]) + 2}" height="{ch + 2}" class="ink" stroke-width="2.2"/>')
        f.text(ox + lm - 6, oy + tm + len(p["series"]) * ch + 14, "series ohm (22 boxed)", "start")
    return f.svg()


def kr260(fig: dict, layout: str) -> str:
    D = fig["data"]
    meas = [p for p in D["ports"] if p["assumption"] == "measured"]
    asm = {p["port"]: p for p in D["ports"] if p["assumption"] == "assumed"}
    wide = layout == "wide"
    w = 640 if wide else 360
    ph = 230
    panel_w = w / 2 if wide else w
    top = 18
    wave_h = ph
    bar_y0 = (top + wave_h + 64) if wide else (top + 2 * (wave_h + 8) + 64)
    h = bar_y0 + 400
    f = Fig(f"kr{layout}", w, int(h), "KR260 ports A and B: as set, best as built and optimal",
            "Receiver waveforms for the two PL Ethernet transmit groups of the KR260 under three settings, and the time each spends beyond the 0.2 V limit.")
    for i, p in enumerate(meas):
        ox, oy = (i * panel_w, top) if wide else (0, top + i * (wave_h + 8))
        pan = {"y_lo": -0.5, "y_hi": 3.4, "limit_over_v": 1.8 + D["limit_v"], "limit_under_v": -D["limit_v"], "vcco_v": 1.8, "yticks": [0.0, 1.8], "xticks": [0, 4, 8]}
        f.text(ox + 36, oy - 6, f'Port {p["port"]}, {g(p["length_in"])} in on the carrier')
        lines = [(a, ANS_DASH[a], 2.0 if a == "xdc" else 1.6, p["waves"][a]["rise"], p["waves"][a]["fall"]) for a in ("xdc", "as_built", "optimal")]
        _wave_panel(f, pan, ox, oy, panel_w, wave_h, layout, lines)
    ky = (top + wave_h + 40) if wide else (top + 2 * (wave_h + 8) + 22)
    _key(f, 40 if wide else 8, ky, [(ANS_NAME[a], ANS_DASH[a], 2.0 if a == "xdc" else 1.6) for a in ("xdc", "as_built", "optimal")], 3 if wide else 1, 190)
    # bars: time beyond the limit, ns
    by = bar_y0
    y = wrap_text(f, 4, by - 14, f'Time beyond the {g(D["limit_v"])} V limit at the worst corner, ns (unit interval {g(meas[0]["ui_ns"])} ns)', layout)
    by = y + 2
    lab_w = 220 if wide else 8
    xmax = max(max(a["t_over_ns"], a["t_under_ns"]) for p in D["ports"] for a in p["answers"].values())
    sc = (w - lab_w - 50) / max(xmax, 0.1)
    y = by
    for p in meas:
        a_ = asm[p["port"]]
        rows = [(f'Port {p["port"]}, as set, {g(a_["length_in"])} in (assumed)', a_["answers"]["xdc"]),
                (f'Port {p["port"]}, as set, {g(p["length_in"])} in (measured)', p["answers"]["xdc"]),
                (f'Port {p["port"]}, best as built', p["answers"]["as_built"]),
                (f'Port {p["port"]}, optimal, {g(p["answers"]["optimal"]["series_ohm"])} ohm', p["answers"]["optimal"])]
        for lab, a in rows:
            t = max(a["t_over_ns"], a["t_under_ns"])
            if wide:
                f.text(4, y + 12, lab)
            else:
                f.text(4, y + 12, lab)
                y += 17
            f.add(f'<rect x="{lab_w}" y="{y + 2}" width="{max(t * sc, 1.5):.1f}" height="12" class="fillink"/>')
            f.text(lab_w + max(t * sc, 1.5) + 4, y + 12, g(t))
            y += 20
        y += 10
    f.h = int(y + 4)
    return f.svg()


def rout(fig: dict, layout: str) -> str:
    D = fig["data"]
    P = D["panels"]
    wide = layout == "wide"
    pw, ph = (212, 230) if wide else (360, 220)
    w = pw * len(P) if wide else 360
    h = ph + 80 if wide else len(P) * ph + 100
    f = Fig(f"ro{layout}", int(w), int(h), "Output resistance against DRIVE",
            "Pull-up output resistance in a 50 ohm load against DRIVE, for three I/O standards, SLOW and FAST, with the weak and strong corner as a bar.")
    mark = {"SLOW": "o", "MEDIUM": "s", "FAST": "d"}
    ymax = 160.0
    for i, p in enumerate(P):
        ox, oy = (i * pw, 0) if wide else (0, i * ph)
        pad_l, pad_t, pad_b = 36, 28, 28
        plw, plh = pw - pad_l - 8, ph - pad_t - pad_b
        f.text(ox + 4, oy + 16, p["label"])
        nd = len(p["drives"])
        sx = lambda d_: ox + pad_l + (p["drives"].index(d_) + 0.5) / nd * plw
        sy = lambda v: oy + pad_t + (ymax - v) / ymax * plh
        f.add(f'<rect x="{ox + pad_l}" y="{oy + pad_t}" width="{plw}" height="{plh}" class="ink" stroke-width="1"/>')
        for v in (0, 50, 100, 150):
            f.add(f'<line x1="{ox + pad_l}" y1="{sy(v):.1f}" x2="{ox + pad_l + plw}" y2="{sy(v):.1f}" class="rule"/>')
            f.text(ox + pad_l - 4, sy(v) + 4, g(v), "end")
        z0, tg = D["z0_ohm"], D["target_ohm"]
        f.add(f'<line x1="{ox + pad_l}" y1="{sy(z0):.1f}" x2="{ox + pad_l + plw}" y2="{sy(z0):.1f}" class="ink" stroke-width="1.4" stroke-dasharray="7 3"/>')
        f.add(f'<line x1="{ox + pad_l}" y1="{sy(tg):.1f}" x2="{ox + pad_l + plw}" y2="{sy(tg):.1f}" class="ink" stroke-width="1" stroke-dasharray="2 3"/>')
        for d_ in p["drives"]:
            f.text(sx(d_), oy + pad_t + plh + 14, d_, "middle")
        f.text(ox + pad_l + plw / 2, oy + pad_t + plh + 26, "DRIVE, mA", "middle")
        off = {s: (k - (len(p["slews"]) - 1) / 2) * 7 for k, s in enumerate(p["slews"])}
        for pt in p["points"]:
            x = sx(pt["drive"]) + off[pt["slew"]]
            f.add(f'<line x1="{x:.1f}" y1="{sy(min(pt["weak"], ymax)):.1f}" x2="{x:.1f}" y2="{sy(pt["strong"]):.1f}" class="ink" stroke-width="1"/>')
            y = sy(pt["typ"])
            m = mark[pt["slew"]]
            if m == "o":
                f.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" class="ink" stroke-width="1.4" style="fill:var(--bg)"/>')
            elif m == "s":
                f.add(f'<rect x="{x - 3:.1f}" y="{y - 3:.1f}" width="6" height="6" class="ink" stroke-width="1.4" style="fill:var(--bg)"/>')
            else:
                f.add(f'<path d="M{x:.1f} {y - 4:.1f} L{x + 4:.1f} {y:.1f} L{x:.1f} {y + 4:.1f} L{x - 4:.1f} {y:.1f} Z" class="fillink"/>')
    # key at the bottom
    ky = ph + 14 if wide else len(P) * ph + 12
    kx = 8
    for s in ("SLOW", "MEDIUM", "FAST"):
        f.text(kx, ky + 4, {"SLOW": "o SLOW", "MEDIUM": "s MEDIUM", "FAST": "d FAST"}[s].replace("o ", "○ ").replace("s ", "□ ").replace("d ", "◆ "))
        kx += 92 if wide else 110
    y = wrap_text(f, 8, ky + 22, f"Marker: typical corner; bar: weak to strong corner. Dashed lines: Z0 ({g(D['z0_ohm'])} ohm) and Z0 less {g(D['series_ohm'])} ohm ({g(D['target_ohm'])} ohm).", layout)
    f.h = int(y + 4)
    return f.svg()


RENDER = {"waveforms": waveforms, "sweep": sweep, "kr260": kr260, "rout": rout}


def render(kind: str, fig: dict, layout: str) -> str:
    return RENDER[kind](fig, layout)
