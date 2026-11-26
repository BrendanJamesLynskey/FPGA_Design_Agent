#!/usr/bin/env python3
"""Collect the brief 91 results into summary.json and draw the figures (plain SVG, monochrome, no glow).

    python3 results/b91/summary.py           # write summary.json and the SVGs
    python3 results/b91/summary.py --check   # fail if they are out of date

Inputs (all committed): accuracy.json, frozen.json, ooc/<k26|a7>/<module>.json, rounds/*.json, and the brief 87 and 89
summaries for the reference points. Latency = clocks x max(closed period, 2.0 ns).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

R = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flow import fmax_cap  # noqa: E402  (brief 201: clock-buffer cap on the closed-clock Fmax)
FLOOR = 2.0
PARTS = {"k26": "xck26-sfvc784-2LV-c", "a7": "xc7a100tcsg324-1"}
MARK = {"binary": "circle", "ternary": "square", "int4": "diamond", "mxfp4": "triangle", "log4": "cross", "log4p1": "plus"}


def j(p):
    return json.loads(Path(p).read_text())


def hw():
    out = {}
    for tag in PARTS:
        for f in sorted((R / "ooc" / tag).glob("*.json")) if (R / "ooc" / tag).exists() else []:
            r = j(f)
            a = r["at_closed_clock"]
            if a and r["closed_at_ns"] < FLOOR:       # quote area from the build at the quoted clock
                at = [x for x in r["passes"] if x.get("closed") and abs(x["clock_ns"] - FLOOR) < 1e-9]
                if at:
                    a = dict(at[0], area_at_ns=FLOOR)
            out.setdefault(r["arm"], {})[tag] = None if not a else {
                "clocks": r["latency_clocks"], "closed_at_ns": round(r["closed_at_ns"], 2), "fmax_mhz": r["closed_at_mhz"],
                **fmax_cap.restate(tag, r["closed_at_mhz"], "closed clock of the search (setup, hold, primitive pulse width)"),
                "latency_ns": round(r["latency_clocks"] * max(r["closed_at_ns"], FLOOR), 2),
                "lut": a["lut"], "ff": a["ff"], "dsp": a["dsp"], "bram_tiles": a["bram_tiles"], "wns_ns": a["wns_ns"],
                "wpws_ns": a["wpws_ns"], "tool": r["tool"], "area_from_build_at_ns": round(a.get("area_at_ns", r["closed_at_ns"]), 2)}
    return out


def family(fmt):
    return "binary" if fmt.startswith("binary") else ("log4" if fmt in ("log4", "log4_nz") else fmt)


def front(pts):
    """pts: [(cost, accuracy, id)]; on the front if no other point has cost <= and accuracy >= with one strict."""
    on = []
    for c, a, i in pts:
        if not any((c2 <= c and a2 >= a) and (c2 < c or a2 > a) for c2, a2, k in pts if k != i):
            on.append(i)
    return on


def build():
    acc, h = j(R / "accuracy.json"), hw()
    fz = {n["id"]: n for n in j(R / "frozen.json")["networks"]}
    rows = []
    for nid, a in acc["networks"].items():
        t = next(r for r in a["runs"] if r["seed"] == a["built_seed"])["test"]
        for pipe in fz[nid]["pipes"]:
            mod = f"lb_{nid}_{pipe}"
            if mod in h:
                rows.append({"module": mod, "network": nid, "format": a["format"], "shape": a["shape"], "act_bits": a["act_bits"],
                             "pipe": pipe, "test_accuracy": t["mean"], "ci95": t["ci95"], "test_mean_over_seeds": a["test_mean_over_seeds"],
                             **{p: h[mod].get(p) for p in PARTS}})
    b87, b89 = j(R.parent / "b87" / "summary.json"), j(R.parent / "b89" / "summary.json")
    refs = [{"id": f"87 {r['arm']}", "test_accuracy": r["test_accuracy"], "k26": {"latency_ns": r["latency_ns"], "lut": r["lut"], "ff": r["ff"]}}
            for r in b87["rows"] if r["arm"] in ("gbt_comb", "mlp_hand", "lutnet", "imb_rule")]
    refs += [{"id": f"89 {r['module']}", "test_accuracy": r["test_accuracy"],
              "k26": {k: r["k26"][k] for k in ("latency_ns", "lut", "ff")}} for r in b89["rows"] if r.get("k26")]
    allp = [(r["k26"]["lut"], r["test_accuracy"], r["module"]) for r in rows if r.get("k26")] + \
           [(r["k26"]["lut"], r["test_accuracy"], r["id"]) for r in refs]
    allt = [(r["k26"]["latency_ns"], r["test_accuracy"], r["module"]) for r in rows if r.get("k26")] + \
           [(r["k26"]["latency_ns"], r["test_accuracy"], r["id"]) for r in refs]
    return {"schema": "b91-summary/1", "latency_rule": f"clocks x max(closed period, {FLOOR} ns)", "parts": PARTS, "rows": rows,
            "references": refs, "fronts_k26": {"accuracy_vs_luts": front(allp), "accuracy_vs_latency": front(allt)},
            "networks": {k: {kk: v[kk] for kk in ("format", "shape", "act_bits", "built_seed", "test_mean_over_seeds", "paired_vs")} |
                         {"test_by_seed": [r["test"]["mean"] for r in v["runs"]], "val_by_seed": [r["val"] for r in v["runs"]]}
                         for k, v in acc["networks"].items()},
            "reference_accuracy": {k: {"mean": v["mean"], "ci95": v["ci95"]} for k, v in acc["references"].items()},
            "rounds": {f.stem: j(f) for f in sorted((R / "rounds").glob("*.json"))}}


CSS = ("<style>.bg{fill:#fff}text{font:12px sans-serif;fill:#222}.ax{stroke:#222;stroke-width:1}.g{stroke:#ccc;stroke-width:.5}"
       ".m{fill:#222;stroke:#222;stroke-width:1.2}.o{fill:#fff;stroke:#222;stroke-width:1.2}.d{stroke:#888;stroke-dasharray:4 3}"
       ".f{stroke:#222;stroke-width:1;fill:none}"
       "@media (prefers-color-scheme:dark){.bg{fill:#111}text{fill:#ddd}.ax{stroke:#ddd}.m{fill:#ddd;stroke:#ddd}.o{fill:#111;stroke:#ddd}"
       ".g{stroke:#444}.f{stroke:#ddd}}</style>")


def marker(kind, x, y, cls):
    if kind == "square":
        return f'<rect class="{cls}" x="{x - 4:.1f}" y="{y - 4:.1f}" width="8" height="8"/>'
    if kind == "diamond":
        return f'<polygon class="{cls}" points="{x:.1f},{y - 5:.1f} {x + 5:.1f},{y:.1f} {x:.1f},{y + 5:.1f} {x - 5:.1f},{y:.1f}"/>'
    if kind == "triangle":
        return f'<polygon class="{cls}" points="{x:.1f},{y - 5:.1f} {x + 5:.1f},{y + 4:.1f} {x - 5:.1f},{y + 4:.1f}"/>'
    if kind == "cross":
        return f'<path class="{cls}" d="M{x - 4:.1f} {y - 4:.1f}L{x + 4:.1f} {y + 4:.1f}M{x - 4:.1f} {y + 4:.1f}L{x + 4:.1f} {y - 4:.1f}" fill="none"/>'
    if kind == "plus":
        return f'<path class="{cls}" d="M{x - 5:.1f} {y:.1f}L{x + 5:.1f} {y:.1f}M{x:.1f} {y - 5:.1f}L{x:.1f} {y + 5:.1f}" fill="none"/>'
    return f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="4"/>'


def plot(title, xs, ys, pts, xlab, ylab, hl, logx, frontline):
    W, H, L, B, T, Rm = 700, 420, 64, 48, 36, 190
    fx = (lambda v: math.log10(v)) if logx else (lambda v: v)
    X = lambda v: L + (fx(v) - fx(xs[0])) / (fx(xs[1]) - fx(xs[0])) * (W - L - Rm)
    Y = lambda v: H - B - (v - ys[0]) / (ys[1] - ys[0]) * (H - B - T)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img">', CSS, f'<rect class="bg" width="{W}" height="{H}"/>',
         f'<text x="{L}" y="20" style="font-weight:bold">{title}</text>',
         f'<line class="ax" x1="{L}" y1="{H - B}" x2="{W - Rm}" y2="{H - B}"/><line class="ax" x1="{L}" y1="{T}" x2="{L}" y2="{H - B}"/>',
         f'<text x="{(L + W - Rm) / 2}" y="{H - 10}" text-anchor="middle">{xlab}</text>',
         f'<text transform="translate(16 {(T + H - B) / 2}) rotate(-90)" text-anchor="middle">{ylab}</text>']
    for i in range(6):
        yv = ys[0] + (ys[1] - ys[0]) * i / 5
        s.append(f'<line class="g" x1="{L}" y1="{Y(yv):.1f}" x2="{W - Rm}" y2="{Y(yv):.1f}"/><text x="{L - 6}" y="{Y(yv) + 4:.1f}" text-anchor="end">{yv:.3f}</text>')
    lo, hi = math.floor(math.log10(xs[0])), math.ceil(math.log10(xs[1]))
    for e in range(lo, hi + 1):
        for m in (1, 2, 5):
            xv = m * 10 ** e
            if xs[0] <= xv <= xs[1]:
                s.append(f'<line class="g" x1="{X(xv):.1f}" y1="{T}" x2="{X(xv):.1f}" y2="{H - B}"/><text x="{X(xv):.1f}" y="{H - B + 16}" text-anchor="middle">{xv:g}</text>')
    s.append(f'<line class="d" x1="{L}" y1="{Y(hl[0]):.1f}" x2="{W - Rm}" y2="{Y(hl[0]):.1f}"/><text x="{W - Rm + 4}" y="{Y(hl[0]) + 4:.1f}">{hl[1]}</text>')
    fp = sorted((x, y) for x, y, _, _, f in pts if f)
    if len(fp) > 1:
        s.append('<polyline class="f" points="' + " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in fp) + '"/>')
    for x, y, lab, kind_filled, _ in pts:
        kind, filled = kind_filled
        s.append(marker(kind, X(x), Y(y), "m" if filled else "o") + (f'<text x="{X(x) + 7:.1f}" y="{Y(y) - 6:.1f}" style="font-size:10px">{lab}</text>' if lab else ""))
    ly = T + 4
    for k, v in MARK.items():
        s.append(marker(v, W - Rm + 14, ly, "m") + f'<text x="{W - Rm + 26}" y="{ly + 4}">{k}</text>')
        ly += 16
    s.append(marker("circle", W - Rm + 14, ly, "o") + f'<text x="{W - Rm + 26}" y="{ly + 4}">brief 87 / 89 (K26)</text>')
    s.append(f'<text x="{W - Rm + 6}" y="{ly + 20}" style="font-size:10px">line: front (all points)</text></svg>')
    return "\n".join(s) + "\n"


def figures(sm):
    figs = {}
    for key, xk, name, xlab, logx in (("accuracy_vs_luts", "lut", "accuracy_vs_luts.svg", "K26 LUTs (log scale)", True),
                                      ("accuracy_vs_latency", "latency_ns", "accuracy_vs_latency.svg", "K26 latency, ns (clocks x max(period, 2.0 ns), log scale)", True)):
        on = set(sm["fronts_k26"][key])
        pts = []
        for r in sm["rows"]:
            if r.get("k26"):
                short = r["format"] + ("" if r["act_bits"] == 4 else f" A{r['act_bits']}") + ("" if r["pipe"] == "comb" else " reg")
                pts.append((r["k26"][xk], r["test_accuracy"], short if r["act_bits"] == 4 and r["pipe"] == "comb" else "",
                            (MARK[family(r["format"])], True), r["module"] in on))
        for r in sm["references"]:
            pts.append((r["k26"][xk], r["test_accuracy"], r["id"] if r["id"] in ("87 imb_rule", "87 gbt_comb", "87 mlp_hand", "89 lg_small_comb", "89 lg_b87_comb", "89 treelut_arm", "89 lg_add_comb") else "", ("circle", False), r["id"] in on))
        if pts:
            xs = (min(p[0] for p in pts) * 0.8, max(p[0] for p in pts) * 1.5)
            figs[name] = plot(f"Test accuracy against {'LUTs' if xk == 'lut' else 'latency'} on the K26 (out of context, Vivado 2026.1)",
                              xs, (0.40, 0.51), pts, xlab, "test accuracy (built seed)",
                              (sm["reference_accuracy"]["trivial_rule_87"]["mean"], "trivial rule"), logx, True)
    return figs


def main():
    sm = build()
    outs = {R / "summary.json": json.dumps(sm, indent=1) + "\n"} | {R / k: v for k, v in figures(sm).items()}
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
