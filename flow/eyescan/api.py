"""A small JSON API over eye-scan captures, for the displays here and for other tools (the navigator of brief 103 reuses it for an eye view and a 3-D bathtub surface).

Every function takes a loaded capture (`capture.load`) and returns plain JSON-able data computed from the raw counts; nothing is stored back. `page_data` is the one
structure the interactive page draws (all of its numbers come from here, the page computes nothing). The CLI form is `python -m flow.eyescan api <capture> --what ...`.
"""

from __future__ import annotations

from typing import Any

from flow.eyescan import capture as C

DEPTHS = [10.0 ** -n for n in range(3, 13)]            # 1e-3 .. 1e-12, one per decade


def eye(cap: dict[str, Any], depth: float = 1e-9) -> dict[str, Any]:
    return C.eye_at(cap, depth)


def bathtub(cap: dict[str, Any], axis: str = "h") -> list[dict[str, Any]]:
    if axis not in ("h", "v"):
        raise ValueError("axis is 'h' or 'v'")
    return C.bathtub_h(cap) if axis == "h" else C.bathtub_v(cap)


def surface(cap: dict[str, Any]) -> dict[str, Any]:
    return C.surface(cap)


def summary(cap: dict[str, Any], depth: float = 1e-9) -> dict[str, Any]:
    return C.summary(cap, depth)


def margin(cap: dict[str, Any], depth: float = 1e-9, min_width_ui: float = 0.3, min_height_mv: float = 30.0) -> dict[str, Any]:
    """Width and height at `depth` against stated thresholds (the agent's `eye_scan` tool). `pass` is true only when both measures exist and meet the thresholds, and the
    capture is not synthetic; the reasons say why not."""
    reasons = []
    nd = C.no_data_stats(cap)
    if nd["no_data"]:
        why = f"NO DATA: {nd['timed_out']}/{nd['points']} points timed out or counted no samples; no eye was measured"
        if not cap["points"]:
            return {"depth": depth, "width_ui": None, "height_mv": None, "width_margin_ui": None, "height_margin_mv": None, "thresholds": {"width_ui": min_width_ui, "height_mv": min_height_mv},
                    "pass": False, "reasons": [why], "equaliser": cap["settings"]["equaliser"], "post_equaliser": True, "note": "no point was measured"}
        reasons.append(why)
    e = C.eye_at(cap, depth)
    if cap.get("synthetic"):
        reasons.append("the capture is SYNTHETIC (offline model), not a measurement")
    if not C.is_complete(cap):
        reasons.append("the scan is incomplete or ended with an error (run.error, points taken against the grid): width and height are not trustworthy")
    elif e["row_v"] != 0 or e["col_h"] != 0:
        reasons.append(f"the grid has no point at 0 mV / 0 UI (nearest row {e['row_v']}, column {e['col_h']})")
    if e.get("width_ui") is None:
        reasons.append(f"no open points along the horizontal row at BER {depth:g}")
    elif e["width_ui"] < min_width_ui:
        reasons.append(f"eye width {e['width_ui']:.3f} UI is below the threshold {min_width_ui} UI")
    if e.get("height_mv") is None:
        reasons.append(f"no open points along the vertical column at BER {depth:g}")
    elif e["height_mv"] < min_height_mv:
        reasons.append(f"eye height {e['height_mv']:.1f} mV is below the threshold {min_height_mv} mV")
    if e["counts"]["shallow"]:
        reasons.append(f"{e['counts']['shallow']} points did not reach depth {depth:g}")
    if not cap.get("restore", {}).get("ok", False):
        reasons.append("the scan did not confirm that the DRP words were restored")
    if cap.get("link", {}).get("ok_throughout") is False:
        reasons.append("the link was not locked throughout the scan")
    return {"depth": depth, "width_ui": e.get("width_ui"), "height_mv": e.get("height_mv"), "width_margin_ui": None if e.get("width_ui") is None else e["width_ui"] - min_width_ui,
            "height_margin_mv": None if e.get("height_mv") is None else e["height_mv"] - min_height_mv, "thresholds": {"width_ui": min_width_ui, "height_mv": min_height_mv},
            "pass": not reasons, "reasons": reasons, "equaliser": cap["settings"]["equaliser"], "post_equaliser": True,
            "note": "measured by the receiver's own eye-scan counters AFTER the equaliser (a statistical eye of the margin inside the receiver, not the eye at the pins)"}


def page_data(cap: dict[str, Any], default_depth: float | None = None) -> dict[str, Any]:
    """Everything the interactive page draws, for one capture: the grid, every point in capture order with its raw counts and BER, the per-depth classification and
    width/height, the two bathtubs and the surface."""
    st = cap["settings"]
    pts = C.flat_points(cap)
    hs = sorted({q["h"] for q in pts})
    vs = sorted({q["v"] for q in pts})
    order = {}
    for i, p in enumerate(cap["points"]):                    # first appearance of each (h, v) in the capture's order
        order.setdefault((p["h"], p["v"]), i)
    ix = {(q["h"], q["v"]): q for q in pts}
    depths = []
    for d in DEPTHS:
        e = C.eye_at(cap, d)
        cls = ["".join({"open": "o", "closed": "c", "shallow": "s", "unmeasured": "u"}[C.classify(ix[(h, v)], d)] if (h, v) in ix else "u" for h in hs) for v in vs]
        depths.append({"depth": d, "n": round(-__import__("math").log10(d)), "rows": cls, "eye": e})
    cells = []
    for v in vs:
        for h in hs:
            q = ix.get((h, v))
            if q is None:
                continue
            cells.append({"h": h, "v": v, "i": order.get((h, v), 0), "err": q["err"], "bits": q["bits"], "ber": q["ber"], "ub": q["ber_ub"], "m": q["measured"],
                          "ut": q["ut"]})
    sm = C.summary(cap, default_depth or st["target_ber"])
    return {"schema": "fda-eye-page-data/1", "label": cap.get("label"), "synthetic": bool(cap.get("synthetic")), "created": cap.get("created"),
            "settings": {k: st[k] for k in ("line_rate_gbps", "equaliser", "data_width", "rxout_div", "ui_per_count", "vs_range", "mv_per_code", "target_ber", "min_errors", "hstep", "vstep", "tx") if k in st},
            "h": hs, "v": vs, "ui": [h * st["ui_per_count"] for h in hs], "mv": [v * C.MV_PER_CODE[st["vs_range"]] for v in vs], "cells": cells, "depths": depths,
            "bath_h": C.bathtub_h(cap), "bath_v": C.bathtub_v(cap), "surface": C.surface(cap),
            "conditions": cap.get("conditions", {}), "restore_ok": cap.get("restore", {}).get("ok"), "link_ok_throughout": cap.get("link", {}).get("ok_throughout"),
            "run": cap.get("run", {}), "ppm": st.get("ppm_offset"), "default_n": round(-__import__("math").log10(default_depth or st["target_ber"])), "summary": sm}
