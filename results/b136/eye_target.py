#!/usr/bin/env python3
"""Brief 136, scenario 6: the human sets the eye width target at 0.75 UI (BER 1e-9). What the recorded eye scans (brief 96D, board run 2026-11-20 10:51) say about it.

Reads the committed captures with flow.eyescan.capture (the same code that wrote summary.txt) and adds two things the summary does not show:
  - the grid's own resolution: hstep 2 counts of 0.015625 UI = 0.03125 UI, so width is known only to that grid (capture.eye_at gives width_ui_lo/hi);
  - a log-linear interpolation of the bathtub edge between the last open point and the first closed point (an ESTIMATE under an assumption, not a measurement).

    python3 results/b136/eye_target.py     # writes results/b136/eye_target.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R.parent))
from flow.eyescan import capture as C  # noqa: E402

TARGET_UI = 0.75
DIR = R / "b96d" / "hw" / "20261120_105134"
DEPTH = 1e-9


def edge_estimate(cap: dict, depth: float) -> dict:
    """Interpolate log10(BER) linearly in h between the last open point and its closed neighbour on each side of the row v = 0 and report where BER crosses `depth`."""
    pts = {q["h"]: q for q in C.flat_points(cap) if q["v"] == 0 and q["measured"]}
    hs = sorted(pts)
    cls = {h: C.classify(pts[h], depth) for h in hs}
    eye = C.eye_at(cap, depth)
    lo, hi = eye["h_open"]
    ui = cap["settings"]["ui_per_count"]

    def cross(open_h: int, closed_h: int):
        qo, qc = pts[open_h], pts[closed_h]
        if cls[closed_h] != "closed" or not qc["ber"]:
            return None
        # the open point has no errors seen: its BER is only bounded (ub); use the bound as its log value (conservative: puts the edge nearer the closed point)
        bo = qo["ber"] if qo["ber"] and qo["ber"] > 0 else qo["ber_ub"]
        x0, y0, x1, y1 = open_h, math.log10(bo), closed_h, math.log10(qc["ber"])
        return x0 + (math.log10(depth) - y0) * (x1 - x0) / (y1 - y0)

    step = min(b - a for a, b in zip(hs, hs[1:]))
    right = cross(hi, hi + step)
    left = cross(lo, lo - step)
    est = None if right is None or left is None else (right - left) * ui
    return dict(open_run_counts=[lo, hi], right_edge_counts=right, left_edge_counts=left, width_ui_interpolated=est,
                neighbours={"closed_right": {"h": hi + step, "ber": pts[hi + step]["ber"]}, "closed_left": {"h": lo - step, "ber": pts[lo - step]["ber"]},
                            "last_open_right": {"h": hi, "ber_ub": pts[hi]["ber_ub"], "ber": pts[hi]["ber"]}, "last_open_left": {"h": lo, "ber_ub": pts[lo]["ber_ub"], "ber": pts[lo]["ber"]}})


def main() -> None:
    rows = []
    for name in ["lpm_1", "lpm_2", "lpm_3", "lpm_4", "dfe_1", "tx_d16", "tx_d8", "tx_post4", "tx_post8", "tx_pre4"]:
        cap = json.loads((DIR / f"{name}.json").read_text())
        depth = cap["settings"]["target_ber"]
        e = C.eye_at(cap, depth)
        row = dict(scan=name, record=f"results/b96d/hw/20261120_105134/{name}.json", equaliser=cap["settings"]["equaliser"], tx=cap["settings"]["tx"], depth=depth,
                   width_ui=e["width_ui"], width_ui_lo=e["width_ui_lo"], width_ui_hi=e["width_ui_hi"], height_mv=e.get("height_mv"),
                   hstep_counts=cap["settings"]["hstep"], ui_per_count=cap["settings"]["ui_per_count"], grid_step_ui=cap["settings"]["hstep"] * cap["settings"]["ui_per_count"])
        row["at_bound_0_5_ui_pass"] = e["width_ui"] >= 0.5
        row["target_0_75_ui_pass_as_measured"] = e["width_ui"] >= TARGET_UI
        row["comparable_to_target"] = depth <= DEPTH
        if depth <= DEPTH:
            row["bathtub_interpolation"] = edge_estimate(cap, depth)
        rows.append(row)
    out = dict(schema="fda.b136.eye_target/1", target_ui=TARGET_UI, depth=DEPTH, current_bound_ui=0.5, current_bound_source="designs/b96_kr260_10g/verif/testplan.yaml V-HW-EYESCAN performance bound", scans=rows,
               not_measured=["no equaliser or TX setting was scanned at BER 1e-9 other than LPM (default) and DFE depth 1", "the tx_* scans ran to BER 1e-7 only, so they cannot show a 1e-9 width",
                             "no finer grid (hstep 1) and no repeat on a second module, temperature or fibre", "no board run in brief 136"])
    (R / "b136" / "eye_target.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    for r in rows:
        print(f"{r['scan']:9s} {r['equaliser']:4s} depth {r['depth']:g}: width {r['width_ui']} UI [{r['width_ui_lo']}, {r['width_ui_hi']}]  grid {r['grid_step_ui']}  >=0.75 {r['target_0_75_ui_pass_as_measured']}  interp {r.get('bathtub_interpolation',{}).get('width_ui_interpolated')}")


if __name__ == "__main__":
    main()
