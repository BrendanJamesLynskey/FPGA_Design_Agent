#!/usr/bin/env python3
"""Collect the brief 89 results into summary.json and draw the three figures (plain SVG, monochrome).

    python3 results/b89/summary.py           # write summary.json and the SVGs
    python3 results/b89/summary.py --check   # fail if they are out of date

Inputs (all committed): accuracy.json, ooc/<k26|a7>/<module>.json, rounds/r1-r3.json and fanin.json, diagnosis.json,
the brief 87 results (results/b87/summary.json, accuracy.json). Latency = clocks x max(closed period, 2.0 ns).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

R = Path(__file__).resolve().parent
B87 = R.parent / "b87"
FLOOR = 2.0
PARTS = {"k26": "xck26-sfvc784-2LV-c", "a7": "xc7a100tcsg324-1"}


def j(p):
    return json.loads(Path(p).read_text())


def hw():
    out = {}
    for tag in PARTS:
        for f in sorted((R / "ooc" / tag).glob("*.json")):
            r = j(f)
            a = r["at_closed_clock"]
            out.setdefault(r["arm"], {})[tag] = None if not a else {
                "clocks": r["latency_clocks"], "closed_at_ns": r["closed_at_ns"], "fmax_mhz": r["closed_at_mhz"],
                "latency_ns": round(r["latency_clocks"] * max(r["closed_at_ns"], FLOOR), 2),
                "lut": a["lut"], "ff": a["ff"], "dsp": a["dsp"], "bram_tiles": a["bram_tiles"], "wns_ns": a["wns_ns"],
                "wpws_ns": a["wpws_ns"], "tool": r["tool"]}
    return out


def build():
    acc = j(R / "accuracy.json")
    h = hw()
    rows = []
    for arm, a in acc["arms"].items():
        bs = a["built_seed"]
        t = next(r for r in a["runs"] if r["seed"] == bs)["test"]
        for mod, hh in h.items():
            if mod.startswith(arm + "_"):
                rows.append({"module": mod, "arm": arm, "test_accuracy": t["mean"], "ci95": t["ci95"], **{p: hh.get(p) for p in PARTS}})
    tl = acc["treelut"]["seed0"]
    if "treelut_arm" in h:
        rows.append({"module": "treelut_arm", "arm": "treelut", "test_accuracy": tl["mean"], "ci95": tl["ci95"],
                     **{p: h["treelut_arm"].get(p) for p in PARTS}})
    b87 = j(B87 / "summary.json")
    rounds = {}
    for rn in ("r1", "r2", "r3"):
        f = R / "rounds" / f"{rn}.json"
        if f.exists():
            rounds[rn] = {n: {"val_mean": c["val_mean"], "val_min": c["val_min"],
                              "table_bits": c["runs"][0]["table_bits_total"]} for n, c in j(f)["configs"].items()}
    fan = {}
    if (R / "rounds" / "fanin.json").exists():
        for n, c in j(R / "rounds" / "fanin.json")["configs"].items():
            fan[n] = {"val_seed0": next(r["val"] for r in c["runs"] if r["seed"] == 0),
                      "table_bits": c["runs"][0]["table_bits_total"], "k26": h.get(f"{n}_comb", {}).get("k26")}
    return {"schema": "b89-summary/1", "latency_rule": f"clocks x max(closed period, {FLOOR} ns)", "parts": PARTS,
            "rows": rows, "arms": {k: {kk: v[kk] for kk in ("built_seed", "test_mean_over_seeds", "paired_vs")} | {
                "test_by_seed": [r["test"]["mean"] for r in v["runs"]]} for k, v in acc["arms"].items()},
            "references": {k: {"mean": v["mean"], "ci95": v["ci95"]} for k, v in acc["references"].items()},
            "b87_rows": [{k: r[k] for k in ("arm", "test_accuracy", "latency_ns", "lut", "ff")} for r in b87["rows"]],
            "rounds": rounds, "fanin": fan}


# --------------------------------------------------------------------------------------------------------- figures
CSS = ("<style>text{font:12px sans-serif;fill:#222}.ax{stroke:#222;stroke-width:1}.g{stroke:#ccc;stroke-width:.5}"
       ".m{fill:#222}.o{fill:#fff;stroke:#222;stroke-width:1.2}.l{stroke:#222;stroke-width:1.2;fill:none}"
       ".d{stroke:#888;stroke-dasharray:4 3}"
       "@media (prefers-color-scheme:dark){text{fill:#ddd}.ax{stroke:#ddd}.m{fill:#ddd}.o{fill:#111;stroke:#ddd}"
       ".l{stroke:#ddd}.g{stroke:#444}}</style>")


def plot(title, xs, ys, pts, xlab, ylab, lines=(), hlines=(), logx=False):
    import math
    W, H, L, B, T, Rm = 640, 380, 64, 48, 36, 150
    x0, x1 = xs
    y0, y1 = ys
    fx = (lambda v: math.log10(v)) if logx else (lambda v: v)
    X = lambda v: L + (fx(v) - fx(x0)) / (fx(x1) - fx(x0)) * (W - L - Rm)
    Y = lambda v: H - B - (v - y0) / (y1 - y0) * (H - B - T)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img">', CSS,
         f'<text x="{L}" y="20" style="font-weight:bold">{title}</text>',
         f'<line class="ax" x1="{L}" y1="{H - B}" x2="{W - Rm}" y2="{H - B}"/><line class="ax" x1="{L}" y1="{T}" x2="{L}" y2="{H - B}"/>',
         f'<text x="{(L + W - Rm) / 2}" y="{H - 10}" text-anchor="middle">{xlab}</text>',
         f'<text transform="translate(16 {(T + H - B) / 2}) rotate(-90)" text-anchor="middle">{ylab}</text>']
    nt = 5
    for i in range(nt + 1):
        yv = y0 + (y1 - y0) * i / nt
        s.append(f'<line class="g" x1="{L}" y1="{Y(yv):.1f}" x2="{W - Rm}" y2="{Y(yv):.1f}"/>'
                 f'<text x="{L - 6}" y="{Y(yv) + 4:.1f}" text-anchor="end">{yv:.3g}</text>')
        xv = (10 ** (fx(x0) + (fx(x1) - fx(x0)) * i / nt)) if logx else x0 + (x1 - x0) * i / nt
        s.append(f'<text x="{X(xv):.1f}" y="{H - B + 16}" text-anchor="middle">{xv:.3g}</text>')
    for yv, lab in hlines:
        s.append(f'<line class="d" x1="{L}" y1="{Y(yv):.1f}" x2="{W - Rm}" y2="{Y(yv):.1f}"/>'
                 f'<text x="{W - Rm + 4}" y="{Y(yv) + 4:.1f}">{lab}</text>')
    for ln in lines:
        s.append('<polyline class="l" points="' + " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in ln) + '"/>')
    for x, y, lab, filled in pts:
        c = "m" if filled else "o"
        s.append(f'<circle class="{c}" cx="{X(x):.1f}" cy="{Y(y):.1f}" r="4"/>'
                 f'<text x="{X(x) + 7:.1f}" y="{Y(y) - 6:.1f}">{lab}</text>')
    s.append("</svg>")
    return "\n".join(s) + "\n"


def figures(sm):
    figs = {}
    pts = []
    for r in sm["rows"]:
        k = r.get("k26")
        if k:
            pts.append((k["latency_ns"], r["test_accuracy"], r["module"], r["arm"] != "treelut"))
    for row in j(B87 / "summary.json")["rows"]:
        if row["arm"] in ("gbt_comb", "mlp_hand", "lutnet"):
            pts.append((row["latency_ns"], row["test_accuracy"], f"87 {row['arm']}", False))
    rule = sm["references"]["trivial_rule_87"]["mean"]
    if pts:
        figs["accuracy_vs_latency.svg"] = plot(
            "Test accuracy against latency on the K26 (out of context, Vivado 2026.1)",
            (1, max(p[0] for p in pts) * 1.3), (0.40, 0.51), pts, "latency, ns (log scale; clocks x max(period, 2.0 ns))",
            "test accuracy", hlines=[(rule, "trivial rule")], logx=True)
    fan = sm["fanin"]
    fp = [(int(n[-1]), v["k26"]["lut"], f"fan-in {n[-1]}", True) for n, v in fan.items() if v.get("k26")]
    if fp:
        figs["luts_vs_fanin.svg"] = plot("K26 LUTs against fan-in (24 score tables, 3-bit codes)", (0.5, 4.5),
                                         (0, max(p[1] for p in fp) * 1.15), fp, "fan-in (codes per table)", "LUTs",
                                         lines=[sorted((p[0], p[1]) for p in fp)])
    hist = []
    i = 0
    labels = []
    for rn in ("r1", "r2", "r3"):
        for n, c in sm["rounds"].get(rn, {}).items():
            i += 1
            hist.append((i, c["val_mean"], f"{rn}", True))
            labels.append((i, n))
    if hist:
        svg = plot("Validation accuracy by design configuration (mean of 3 seeds)", (0, i + 1), (0.40, 0.50),
                   [(x, y, "", f) for x, y, _, f in hist], "configuration (r1, r2, r3 in order)", "validation accuracy",
                   hlines=[(0.4489, "rule (in-sample)"), (0.4801, "ceiling (D2)")])
        figs["iteration_history.svg"] = svg
    return figs


def main():
    sm = build()
    figs = figures(sm)
    outs = {R / "summary.json": json.dumps(sm, indent=1) + "\n"} | {R / k: v for k, v in figs.items()}
    if "--check" in sys.argv:
        bad = [str(p) for p, t in outs.items() if not p.exists() or p.read_text() != t]
        print("out of date: " + ", ".join(bad) if bad else "summary current")
        return 1 if bad else 0
    for p, t in outs.items():
        p.write_text(t)
        print("wrote", p.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
