#!/usr/bin/env python3
"""Collect the brief 92 results into summary.json and draw the figures (plain SVG, monochrome, no glow).

    python3 results/b92/summary.py           # write summary.json and the SVGs
    python3 results/b92/summary.py --check   # fail if they are out of date

Inputs (all committed): gen_stats.json, stage1_val.json, stage1_test.json, stage2_frozen.json, stage2_accuracy.json,
determinism.json, ooc/<k26|a7>/<module>.json. Latency = clocks x max(closed period, 2.0 ns) (the brief 87 quoting floor).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

R = Path(__file__).resolve().parent
FLOOR = 2.0
PARTS = {"k26": "xck26-sfvc784-2LV-c", "a7": "xc7a100tcsg324-1"}
BUILT = ["ref_current", "a1_decay", "a4_lut", "a2_win8", "a2_win16"]
LABEL = {"ref_current": "head, no history", "a1_decay": "1 decaying sums", "a4_lut": "4 LUT net on sums", "a2_win8": "2 window N=8",
         "a2_win16": "2 window N=16", "a3_top1": "3 attention top-1", "a3_relu": "3 attention ReLU", "ref_lut": "LUT net, no history",
         "ref_mlp": "87 MLP, no history"}


def j(p):
    return json.loads(Path(p).read_text())


def hw():
    out = {}
    for tag in PARTS:
        d = R / "ooc" / tag
        for f in sorted(d.glob("*.json")) if d.exists() else []:
            r = j(f)
            a = r["at_closed_clock"]
            arm = r["arm"].replace("b92_", "")
            if a and r["closed_at_ns"] < FLOOR:
                at = [x for x in r["passes"] if x.get("closed") and abs(x["clock_ns"] - FLOOR) < 1e-9]
                if at:
                    a = dict(at[0], area_at_ns=FLOOR)
            out.setdefault(arm, {})[tag] = None if not a else {
                "clocks": r["latency_clocks"], "closed_at_ns": round(r["closed_at_ns"], 2), "fmax_mhz": r["closed_at_mhz"],
                "latency_ns": round(r["latency_clocks"] * max(r["closed_at_ns"], FLOOR), 2),
                "lut": a["lut"], "ff": a["ff"], "dsp": a["dsp"], "bram_tiles": a["bram_tiles"], "wns_ns": a["wns_ns"],
                "wpws_ns": a["wpws_ns"], "tool": r["tool"], "area_from_build_at_ns": round(a.get("area_at_ns", r["closed_at_ns"]), 2)}
    return out


def build():
    s1, s2, fz, gs = j(R / "stage1_test.json"), j(R / "stage2_accuracy.json"), j(R / "stage2_frozen.json"), j(R / "gen_stats.json")
    h = hw()
    det = j(R / "determinism.json") if (R / "determinism.json").exists() else {}
    arms = {}
    for a, v in s2["arms"].items():
        t = next(r for r in v["runs"] if r["seed"] == v["built_seed"])["test"]
        arms[a] = {"built_seed": v["built_seed"], "test_accuracy": t["mean"], "ci95": t["ci95"],
                   "test_by_seed": [r["test"]["mean"] for r in v["runs"]], "val_by_seed": [r["val"] for r in v["runs"]],
                   "test_mean_over_seeds": v["test_mean_over_seeds"],
                   "paired_vs": {k: {kk: x[kk] for kk in ("difference_mean", "ci95")} for k, x in v["paired_vs"].items()},
                   "hardware": {tag: h.get(a, {}).get(tag) for tag in PARTS} if a in BUILT else None,
                   "twin_equals_rtl": ({k: (x["n"], x["mismatches"]) for k, x in det[a].items()} if a in det else None)}
    return {"schema": "b92-summary/1", "latency_rule": f"clocks x max(closed period, {FLOOR} ns)", "parts": PARTS,
            "gate": {"generator": "hawkes", "passes": s1["gate"]["passes"],
                     "gate_candidate": {g: s1["generators"][g]["gate_candidate"] for g in s1["generators"]},
                     "gate_difference": {g: s1["generators"][g]["gate_difference"] for g in s1["generators"]},
                     "sensitivity_hist_boosting": {g: s1["generators"][g]["sensitivity_hist_boosting_difference"] for g in s1["generators"]}},
            "generator_statistics": gs, "stage2_rate_set": fz["rate_set"], "arms": arms,
            "references": s2["references"], "attention_vs_decay": s2["attention_vs_decay"]}


CSS = ("<style>.bg{fill:#fff}text{font:12px sans-serif;fill:#222}.ax{stroke:#222;stroke-width:1}.g{stroke:#ccc;stroke-width:.5}"
       ".m{fill:#222;stroke:#222;stroke-width:1.2}.o{fill:#fff;stroke:#222;stroke-width:1.2}.d{stroke:#888;stroke-dasharray:4 3}"
       ".l{stroke:#222;stroke-width:1.5;fill:none}.l2{stroke:#888;stroke-width:1.5;fill:none;stroke-dasharray:5 3}"
       "@media (prefers-color-scheme:dark){.bg{fill:#111}text{fill:#ddd}.ax{stroke:#ddd}.m{fill:#ddd;stroke:#ddd}.o{fill:#111;stroke:#ddd}"
       ".g{stroke:#444}.l{stroke:#ddd}.l2{stroke:#999}}</style>")


def svg_open(W, H, title):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img"><title>{title}</title>', CSS,
            f'<rect class="bg" width="{W}" height="{H}"/>', f'<text x="12" y="20" style="font-weight:bold">{title}</text>']


def fig_accuracy(sm):
    rows = [(LABEL[a], v["test_accuracy"], v["ci95"], "m") for a, v in sm["arms"].items() if a != "ref_lut"]
    refs = [("trivial rule", sm["references"]["trivial_rule"]), ("87 trees, current", sm["references"]["trees_87_current"]),
            ("87 trees, lagged features N=16", sm["references"]["trees_lagfeat16"])]
    rows = [(n, r["mean"], r["ci95"], "o") for n, r in refs] + rows
    W, H, L, T, Rm = 760, 60 + 26 * len(rows), 250, 44, 20
    lo, hi = 0.40, 0.52
    X = lambda v: L + (v - lo) / (hi - lo) * (W - L - Rm)  # noqa: E731
    s = svg_open(W, H, "Test accuracy, self-exciting generator (built seed, 95% interval over 10 test sessions)")
    for i in range(7):
        v = lo + (hi - lo) * i / 6
        s.append(f'<line class="g" x1="{X(v):.1f}" y1="{T - 6}" x2="{X(v):.1f}" y2="{H - 24}"/><text x="{X(v):.1f}" y="{H - 8}" text-anchor="middle">{v:.3f}</text>')
    for k, (n, m, ci, cls) in enumerate(rows):
        y = T + 8 + 26 * k
        s.append(f'<text x="{L - 8}" y="{y + 4}" text-anchor="end">{n}</text>')
        s.append(f'<line class="ax" x1="{X(ci[0]):.1f}" y1="{y}" x2="{X(ci[1]):.1f}" y2="{y}"/><circle class="{cls}" cx="{X(m):.1f}" cy="{y}" r="4.5"/>')
        s.append(f'<text x="{X(ci[1]) + 8:.1f}" y="{y + 4}" style="font-size:10px">{m:.4f}</text>')
    s.append("</svg>")
    return "\n".join(s) + "\n"


def fig_luts(sm):
    pts = []
    for a in BUILT:
        v = sm["arms"][a]
        hwk = (v["hardware"] or {}).get("k26")
        if hwk:
            pts.append((hwk["lut"], v["test_accuracy"], LABEL[a]))
    if not pts:
        return None
    W, H, L, B, T, Rm = 700, 400, 64, 48, 36, 40
    xs = (min(p[0] for p in pts) * 0.5, max(p[0] for p in pts) * 2)
    ys = (0.475, 0.505)
    fx = math.log10
    X = lambda v: L + (fx(v) - fx(xs[0])) / (fx(xs[1]) - fx(xs[0])) * (W - L - Rm)  # noqa: E731
    Y = lambda v: H - B - (v - ys[0]) / (ys[1] - ys[0]) * (H - B - T)  # noqa: E731
    s = svg_open(W, H, "Test accuracy against LUTs on the K26 (out of context, Vivado 2026.1)")
    for i in range(7):
        yv = ys[0] + (ys[1] - ys[0]) * i / 6
        s.append(f'<line class="g" x1="{L}" y1="{Y(yv):.1f}" x2="{W - Rm}" y2="{Y(yv):.1f}"/><text x="{L - 6}" y="{Y(yv) + 4:.1f}" text-anchor="end">{yv:.3f}</text>')
    for e in range(int(math.floor(fx(xs[0]))), int(math.ceil(fx(xs[1]))) + 1):
        for m in (1, 2, 5):
            xv = m * 10 ** e
            if xs[0] <= xv <= xs[1]:
                s.append(f'<line class="g" x1="{X(xv):.1f}" y1="{T}" x2="{X(xv):.1f}" y2="{H - B}"/><text x="{X(xv):.1f}" y="{H - B + 16}" text-anchor="middle">{xv:g}</text>')
    s.append(f'<line class="ax" x1="{L}" y1="{H - B}" x2="{W - Rm}" y2="{H - B}"/><line class="ax" x1="{L}" y1="{T}" x2="{L}" y2="{H - B}"/>')
    s.append(f'<text x="{(L + W - Rm) / 2}" y="{H - 10}" text-anchor="middle">K26 LUTs (log scale)</text>')
    s.append(f'<text transform="translate(16 {(T + H - B) / 2}) rotate(-90)" text-anchor="middle">test accuracy (built seed)</text>')
    for x, y, lab in pts:
        s.append(f'<circle class="m" cx="{X(x):.1f}" cy="{Y(y):.1f}" r="4.5"/><text x="{X(x) + 8:.1f}" y="{Y(y) - 7:.1f}" style="font-size:11px">{lab}</text>')
    s.append("</svg>")
    return "\n".join(s) + "\n"


def fig_acf(sm):
    g = sm["generator_statistics"]
    lags = ["1", "2", "5", "10", "20", "50"]
    W, H, L, B, T, Rm = 640, 360, 64, 48, 36, 120
    ys = (-0.03, 0.2)
    X = lambda i: L + i / (len(lags) - 1) * (W - L - Rm)  # noqa: E731
    Y = lambda v: H - B - (v - ys[0]) / (ys[1] - ys[0]) * (H - B - T)  # noqa: E731
    s = svg_open(W, H, "Trade-sign autocorrelation in trade time (10 test sessions)")
    for i in range(6):
        yv = ys[0] + (ys[1] - ys[0]) * i / 5
        s.append(f'<line class="g" x1="{L}" y1="{Y(yv):.1f}" x2="{W - Rm}" y2="{Y(yv):.1f}"/><text x="{L - 6}" y="{Y(yv) + 4:.1f}" text-anchor="end">{yv:.2f}</text>')
    s.append(f'<line class="ax" x1="{L}" y1="{Y(0):.1f}" x2="{W - Rm}" y2="{Y(0):.1f}"/>')
    for i, lg in enumerate(lags):
        s.append(f'<text x="{X(i):.1f}" y="{H - B + 16}" text-anchor="middle">{lg}</text>')
    s.append(f'<text x="{(L + W - Rm) / 2}" y="{H - 10}" text-anchor="middle">lag in trades</text>')
    for key, cls, lab in (("hawkes", "l", "self-exciting"), ("b87", "l2", "brief 87")):
        a = g[key]["trade_sign_acf"]
        s.append(f'<polyline class="{cls}" points="' + " ".join(f"{X(i):.1f},{Y(a[lg]):.1f}" for i, lg in enumerate(lags)) + '"/>')
        s.append(f'<text x="{W - Rm + 8}" y="{Y(a["1"]) + 4:.1f}" style="font-size:11px">{lab}</text>')
    s.append("</svg>")
    return "\n".join(s) + "\n"


def main():
    sm = build()
    outs = {R / "summary.json": json.dumps(sm, indent=1) + "\n", R / "accuracy_by_arm.svg": fig_accuracy(sm), R / "sign_acf.svg": fig_acf(sm)}
    f = fig_luts(sm)
    if f:
        outs[R / "accuracy_vs_luts.svg"] = f
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
