"""Timing diagrams (SVG, monochrome) for the three arms, from the clocks the integration test measured
(results/b93/integration_gbt_pre{0,1,2,3}_latency.json). Clock 0 is the clock msg_inst_v is high (the instrument field
has just completed, byte offset 3 of the message); the price field completes at clock 4 (msg_px_v), the rule table's
decision is visible at clock 5.

    python -m designs.b93_precompute.model.figures
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
R = ROOT / "results" / "b93"
X0, CW, RH = 190, 64, 34
C0, C1 = -3, 9


def load(pre: int) -> dict:
    d = json.loads((R / f"integration_gbt_pre{pre}_latency.json").read_text())["modes"]["speculative_model_on"]
    return d


def box(row, a, b, text, fill="#fff", dash=False):
    x, y = X0 + (a - C0) * CW, 46 + row * RH
    st = ' stroke-dasharray="4 3"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{(b - a) * CW - 2}" height="{RH - 8}" fill="{fill}" stroke="#222"{st}/>'
            f'<text x="{x + 5}" y="{y + 17}" font-size="11">{text}</text>')


def svg(title: str, rows: list[tuple[str, list]], decision: int, foot: str) -> str:
    w = X0 + (C1 - C0) * CW + 20
    h = 46 + len(rows) * RH + 60
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="sans-serif" role="img" aria-label="{title}">',
         f'<rect width="{w}" height="{h}" fill="#fff"/>', f'<text x="10" y="20" font-size="14" font-weight="bold">{title}</text>']
    for c in range(C0, C1 + 1):
        x = X0 + (c - C0) * CW
        o.append(f'<line x1="{x}" y1="30" x2="{x}" y2="{46 + len(rows) * RH}" stroke="#ddd"/>')
        o.append(f'<text x="{x + 3}" y="40" font-size="10" fill="#555">{c}</text>')
    for i, (lab, boxes) in enumerate(rows):
        o.append(f'<text x="8" y="{46 + i * RH + 17}" font-size="11">{lab}</text>')
        o += [box(i, *b) if len(b) == 3 else box(i, *b) for b in boxes]
    for c, lab in ((4, "price field complete"), (decision, "decision")):
        x = X0 + (c - C0) * CW
        o.append(f'<line x1="{x}" y1="30" x2="{x}" y2="{46 + len(rows) * RH}" stroke="#000" stroke-width="2"/>')
        o.append(f'<text x="{x + 4}" y="{46 + len(rows) * RH + 14 + (0 if c == 4 else 14)}" font-size="11">{lab} (clock {c})</text>')
    o.append(f'<text x="8" y="{h - 8}" font-size="11" fill="#333">{foot}</text></svg>')
    return "\n".join(o) + "\n"


BYTES = [(-3, -2, "type"), (-2, -1, "side"), (-1, 1, "instrument"), (1, 5, "price (4 bytes)"), (5, 9, "size ...")]


def main() -> int:
    b, e, t1, t2 = load(0), load(1), load(2), load(3)
    out = {}
    # clocks are the ones measured; decision = 5 + the gate's added clocks
    out["timing_baseline.svg"] = svg(
        "Arm 1, baseline (87): features and model start at the price field", [
            ("message bytes", BYTES), ("book read", [(0, 1, "read")]),
            ("rule table", [(4, 5, "rules")]),
            ("feature unit", [(4, 5, "features")]), ("model (1 clock)", [(5, 6, "model")]),
            ("gate", [(5, 6, "hold 1")])], 4 + 2 + 0,
        f"measured: class valid {b['class_valid_clocks_after_instrument_field']} clocks after the instrument field, "
        f"{-b['class_valid_clocks_before_rule_fire']} clock after the rule's decision; gate adds {b['stages_cycles']['model gate (rule fire -> decision)']} clock")
    out["timing_early.svg"] = svg(
        "Arm 2, early features: the model finishes before the price does", [
            ("message bytes", BYTES), ("book read", [(0, 1, "read")]),
            ("rule table", [(4, 5, "rules")]),
            ("feature unit", [(1, 2, "features")]), ("model (1 clock)", [(2, 3, "model")]),
            ("gate", [(5, 6, "release")])], 5,
        f"measured: class valid {e['class_valid_clocks_after_instrument_field']} clocks after the instrument field, "
        f"{e['class_valid_clocks_before_rule_fire']} clocks before the rule's decision; gate adds {e['stages_cycles']['model gate (rule fire -> decision)']} clocks")
    out["timing_table.svg"] = svg(
        "Arm 3, table on the late feature (fill 1 clock above, 2 clocks below)", [
            ("message bytes", BYTES), ("book read", [(0, 1, "read")]),
            ("rule table", [(4, 5, "rules")]),
            ("feature unit", [(1, 2, "early feats")]),
            ("table fill (1)", [(2, 3, "fill")]), ("select (1)", [(3, 4, "late: pick")]),
            ("table fill (2)", [(2, 4, "fill, 2 clocks")]), ("select (2)", [(4, 5, "late: pick")]),
            ("gate", [(5, 6, "release")])], 5,
        f"measured: class valid {t1['class_valid_clocks_after_instrument_field']} (fill 1) and "
        f"{t2['class_valid_clocks_after_instrument_field']} (fill 2) clocks after the instrument field; clocks before the rule's decision "
        f"{t1['class_valid_clocks_before_rule_fire']} and {t2['class_valid_clocks_before_rule_fire']}; gate adds 0")
    for n, s in out.items():
        (R / n).write_text(s)
        print("wrote", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
