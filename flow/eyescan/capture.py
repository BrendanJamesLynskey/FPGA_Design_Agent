"""The eye-scan capture ("fda-capture-eye/1") and the numbers derived from it.

The envelope (schema, instrument {kind, driver, settings, mock}, design, build, conditions, created) is that of the common capture format (debug_core/capture.py,
"fda-capture/1"); the payload is a grid of points, not a timeline of samples, so it has its own schema id. Raw counts are the record: every derived number (BER,
width, height, bathtub, surface) is computed from them by this module and is never stored as a measurement.

A point is {"h": offset in counts, "v": signed vertical code, "ut": 0|1, "rungs": [{"pre": ES_PRESCALE, "err": es_error_count, "samp": es_sample_count, "tmo": bool}, ...]}.
Bits examined by one rung = samp x 2^(1+pre) x data_width (32: the receiver's internal width). The point's BER pools the rungs at its final prescale (see `point_stats`).
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

SCHEMA = "fda-capture-eye/1"
#: RX_EYESCAN_VS_RANGE scale, mV per count (UG576 v1.7.1 Table 4-20): 00 1.5, 01 1.8, 10 2.2, 11 2.8.
MV_PER_CODE = (1.5, 1.8, 2.2, 2.8)
#: One-sided 95 % upper bound on the error probability after N error-free trials is -ln(0.05)/N = 2.9957/N ("rule of three": 3/N).
ZERO_ERR_FACTOR = 3.0
ES_COUNT_MAX = 65535


class CaptureError(ValueError):
    pass


def rung_bits(r: dict[str, Any], width: int) -> int:
    """Bits examined by one rung."""
    return int(r["samp"]) * (1 << (1 + int(r["pre"]))) * int(width)


def point_stats(p: dict[str, Any], width: int = 32) -> dict[str, Any]:
    """Raw-derived statistics of a point: the rungs at its final prescale are pooled (the ladder repeats its last rung when the target needs more bits than one saturated
    run at the longest allowed rung); earlier rungs of the ladder are not pooled. A timed-out rung gives no data. With both UT signs (DFE) the caller merges two points
    (`merge_ut`)."""
    rungs = p.get("rungs") or []
    if not rungs or rungs[-1].get("tmo"):
        return {"bits": 0, "err": 0, "ber": None, "ber_ub": None, "measured": False}
    pre = rungs[-1]["pre"]
    final = []
    for r in reversed(rungs):
        if r["pre"] != pre or r.get("tmo"):
            break
        final.append(r)
    bits = sum(rung_bits(r, width) for r in final)
    err = sum(int(r["err"]) for r in final)
    if bits <= 0:
        return {"bits": 0, "err": err, "ber": None, "ber_ub": None, "measured": False}
    return {"bits": bits, "err": err, "ber": err / bits if err else 0.0, "ber_ub": ZERO_ERR_FACTOR / bits if err == 0 else None, "measured": True}


def merge_ut(points: list[dict[str, Any]], width: int = 32, expected_ut: int = 1) -> list[dict[str, Any]]:
    """DFE: UG576 says two measurements, at +UT and -UT, are needed for the total BER at one offset. The merged BER is the EQUAL-WEIGHT MEAN of the two sides' BERs (each side runs
    its own ladder, so their bit counts differ; pooling bits would weight the deeper side). The merged point can vouch only for the SHALLOWER side's bits, so `bits` is the
    minimum; `err` is the sum. When both sides saw no errors the bound is the mean of the two 3/bits bounds. A point that has fewer than `expected_ut` measured sides is unmeasured."""
    by: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for p in points:
        by.setdefault((p["h"], p["v"]), []).append(p)
    out = []
    for (h, v), ps in by.items():
        sts = [point_stats(p, width) for p in ps]
        ok = len(ps) >= expected_ut and all(s["measured"] and s["bits"] > 0 for s in sts)
        if ok:
            bers = [s["err"] / s["bits"] for s in sts]
            err = sum(s["err"] for s in sts)
            ber = sum(bers) / len(bers)
            ub = sum(ZERO_ERR_FACTOR / s["bits"] for s in sts) / len(sts) if err == 0 else None
            out.append({"h": h, "v": v, "ut": [p["ut"] for p in ps], "bits": min(s["bits"] for s in sts), "err": err, "measured": True, "ber_merged": ber, "ub_merged": ub})
        else:
            out.append({"h": h, "v": v, "ut": [p["ut"] for p in ps], "bits": 0, "err": 0, "measured": False, "ber_merged": None, "ub_merged": None})
    return out


def flat_points(cap: dict[str, Any]) -> list[dict[str, Any]]:
    """Points with one entry per (h, v): {"h","v","bits","err","measured","ber","ber_ub"} (UT signs merged)."""
    width = cap["settings"]["data_width"]
    out = []
    for q in merge_ut(cap["points"], width, len(cap["settings"].get("ut_signs", [0]))):
        if q["measured"] and q["bits"] > 0:
            q["ber"] = q["ber_merged"]       # 0.0 means NO ERRORS SEEN: the BER is below `ber_ub`, never zero
            q["ber_ub"] = q["ub_merged"]
        else:
            q["ber"] = None
            q["ber_ub"] = None
        out.append(q)
    return out


def classify(q: dict[str, Any], depth: float) -> str:
    """Point state at BER depth `depth`: 'open' (measured BER at most depth AND enough bits to say so: bits x depth >= 3), 'closed' (measured BER above depth),
    'shallow' (BER at most depth but too few bits to establish it: the point did not reach this depth) or 'unmeasured'."""
    if not q["measured"]:
        return "unmeasured"
    if q["ber"] > depth:
        return "closed"
    return "open" if q["bits"] * depth >= ZERO_ERR_FACTOR else "shallow"


def depth_reached(q: dict[str, Any]) -> float | None:
    """The smallest BER this point can vouch for: 3/bits (95 % bound for zero errors)."""
    return ZERO_ERR_FACTOR / q["bits"] if q.get("measured") and q["bits"] else None


def _run_around(sorted_vals: list[int], open_set: set[int], centre: int) -> tuple[int, int] | None:
    """The contiguous (in grid order) run of open values that contains the open value nearest to `centre`; None if nothing is open."""
    if not open_set:
        return None
    seed = min(open_set, key=lambda x: (abs(x - centre), x))
    i = sorted_vals.index(seed)
    lo = hi = i
    while lo > 0 and sorted_vals[lo - 1] in open_set:
        lo -= 1
    while hi < len(sorted_vals) - 1 and sorted_vals[hi + 1] in open_set:
        hi += 1
    return sorted_vals[lo], sorted_vals[hi]


def eye_at(cap: dict[str, Any], depth: float) -> dict[str, Any]:
    """Eye width (UI) along the row nearest v = 0 and height (codes, mV) along the column nearest h = 0, at BER `depth`. 'open' points only count (see `classify`).
    `width_ui_lo`/`width_ui_hi` are the extremes if the run is widened or narrowed by one grid step each side (the grid resolution, not a statistical bar)."""
    pts = flat_points(cap)
    st = cap["settings"]
    ui_c = st["ui_per_count"]
    mv = MV_PER_CODE[st["vs_range"]]
    hs = sorted({q["h"] for q in pts})
    vs = sorted({q["v"] for q in pts})
    hstep = min((b - a for a, b in zip(hs, hs[1:])), default=1)
    vstep = min((b - a for a, b in zip(vs, vs[1:])), default=1)
    row_v = min(vs, key=lambda x: (abs(x), x))
    col_h = min(hs, key=lambda x: (abs(x), x))
    cls = {(q["h"], q["v"]): classify(q, depth) for q in pts}
    row_open = {h for h in hs if cls.get((h, row_v)) == "open"}
    col_open = {v for v in vs if cls.get((col_h, v)) == "open"}
    rr = _run_around(hs, row_open, 0)
    cr = _run_around(vs, col_open, 0)
    res: dict[str, Any] = {"depth": depth, "row_v": row_v, "col_h": col_h, "counts": {k: sum(1 for c in cls.values() if c == k) for k in ("open", "closed", "shallow", "unmeasured")}}
    if rr:
        w_counts = rr[1] - rr[0]
        res["width_counts"] = w_counts
        res["width_ui"] = w_counts * ui_c
        res["width_ui_lo"] = max(0.0, (w_counts - hstep) * ui_c)
        res["width_ui_hi"] = (w_counts + hstep) * ui_c
        res["h_open"] = [rr[0], rr[1]]
    else:
        res["width_ui"] = None
    if cr:
        h_codes = cr[1] - cr[0]
        res["height_codes"] = h_codes
        res["height_mv"] = h_codes * mv
        res["height_mv_lo"] = max(0.0, (h_codes - vstep) * mv)
        res["height_mv_hi"] = (h_codes + vstep) * mv
        res["v_open"] = [cr[0], cr[1]]
    else:
        res["height_mv"] = None
    res["mv_per_code"] = mv
    res["shallow_note"] = ("some points could not vouch for this depth (too few bits): the eye at this depth is only as wide as the points that reached it; scan deeper (--target-ber) "
                           "or read a shallower depth") if res["counts"]["shallow"] else None
    return res


def bathtub_h(cap: dict[str, Any]) -> list[dict[str, Any]]:
    """Horizontal bathtub: BER against horizontal offset (UI) along the row nearest v = 0. Each entry: h, ui, bits, err, ber (None if unmeasured), ber_ub (zero-error bound)."""
    pts = flat_points(cap)
    ui_c = cap["settings"]["ui_per_count"]
    row_v = min({q["v"] for q in pts}, key=lambda x: (abs(x), x))
    return [{"h": q["h"], "ui": q["h"] * ui_c, "v": q["v"], "bits": q["bits"], "err": q["err"], "ber": q["ber"], "ber_ub": q["ber_ub"]} for q in sorted(pts, key=lambda x: x["h"]) if q["v"] == row_v]


def bathtub_v(cap: dict[str, Any]) -> list[dict[str, Any]]:
    pts = flat_points(cap)
    mv = MV_PER_CODE[cap["settings"]["vs_range"]]
    col_h = min({q["h"] for q in pts}, key=lambda x: (abs(x), x))
    return [{"v": q["v"], "mv": q["v"] * mv, "h": q["h"], "bits": q["bits"], "err": q["err"], "ber": q["ber"], "ber_ub": q["ber_ub"]} for q in sorted(pts, key=lambda x: x["v"]) if q["h"] == col_h]


def surface(cap: dict[str, Any]) -> dict[str, Any]:
    """log10 BER over the grid (the value for a zero-error point is its 3/bits bound, flagged), as rows of v and columns of h."""
    pts = flat_points(cap)
    hs = sorted({q["h"] for q in pts})
    vs = sorted({q["v"] for q in pts})
    ix = {(q["h"], q["v"]): q for q in pts}
    z, bound = [], []
    for v in vs:
        zr, br = [], []
        for h in hs:
            q = ix.get((h, v))
            if q is None or not q["measured"]:
                zr.append(None); br.append(None)
            elif q["err"] == 0:
                zr.append(round(math.log10(q["ber_ub"]), 4)); br.append(True)
            else:
                zr.append(round(math.log10(q["ber"]), 4)); br.append(False)
        z.append(zr); bound.append(br)
    st = cap["settings"]
    return {"h": hs, "ui": [h * st["ui_per_count"] for h in hs], "v": vs, "mv": [v * MV_PER_CODE[st["vs_range"]] for v in vs], "log10_ber": z, "zero_error_bound": bound}


def summary(cap: dict[str, Any], depth: float = 1e-9) -> dict[str, Any]:
    st = cap["settings"]
    pts = flat_points(cap)
    bits = [q["bits"] for q in pts if q["measured"]]
    return {"post_equaliser": True, "complete": is_complete(cap), "schema": cap["schema"], "synthetic": bool(cap.get("synthetic")), "created": cap.get("created"), "label": cap.get("label"),
            "line_rate_gbps": st["line_rate_gbps"], "equaliser": st["equaliser"], "tx": st.get("tx"), "points": len(cap["points"]), "grid_points": len(pts),
            "min_bits_per_point": min(bits) if bits else 0, "max_bits_per_point": max(bits) if bits else 0,
            "deepest_ber_any_point": ZERO_ERR_FACTOR / max(bits) if bits else None, "eye": eye_at(cap, depth),
            "conditions_start": cap.get("conditions", {}).get("start"), "conditions_end": cap.get("conditions", {}).get("end"),
            "restore_ok": cap.get("restore", {}).get("ok"), "link_ok_throughout": cap.get("link", {}).get("ok_throughout")}


def is_complete(cap: dict[str, Any]) -> bool:
    """True only when the scan ended without an error and took every point of its grid (a partial grid has no row at 0 mV, so its width and height would come from another row)."""
    st = cap["settings"]
    exp = st.get("expected_points")
    return cap.get("run", {}).get("error") is None and exp is not None and len(cap["points"]) == exp


REQUIRED = ("schema", "created", "instrument", "design", "settings", "points", "conditions")
REQ_SETTINGS = ("line_rate_gbps", "equaliser", "data_width", "ui_per_count", "vs_range", "rxout_div", "target_ber")


def validate(cap: dict[str, Any]) -> list[str]:
    errs = []
    if cap.get("schema") != SCHEMA:
        errs.append(f"schema is {cap.get('schema')!r}, expected {SCHEMA!r}")
    for k in REQUIRED:
        if k not in cap:
            errs.append(f"missing {k}")
    for k in REQ_SETTINGS:
        if k not in cap.get("settings", {}):
            errs.append(f"settings.{k} missing")
    if errs:
        return errs
    for i, p in enumerate(cap["points"]):
        if not all(k in p for k in ("h", "v", "ut", "rungs")):
            errs.append(f"point {i} lacks h, v, ut or rungs")
            continue
        for r in p["rungs"]:
            if not (0 <= r.get("samp", -1) <= ES_COUNT_MAX and 0 <= r.get("err", -1) <= ES_COUNT_MAX and 0 <= r.get("pre", -1) <= 31):
                errs.append(f"point {i}: rung out of range {r}")
    if cap.get("synthetic") and not cap["instrument"].get("mock"):
        errs.append("a synthetic capture must say instrument.mock = true")
    if not cap.get("synthetic") and cap["instrument"].get("mock"):
        errs.append("instrument.mock is set but the capture is not marked synthetic")
    return errs


def load(path: Path | str) -> dict[str, Any]:
    cap = json.loads(Path(path).read_text())
    bad = validate(cap)
    if bad:
        raise CaptureError(f"{path}: not an {SCHEMA} file: " + "; ".join(bad[:6]))
    return cap


def save(cap: dict[str, Any], path: Path | str) -> Path:
    bad = validate(cap)
    if bad:
        raise CaptureError("refusing to save an invalid capture: " + "; ".join(bad[:6]))
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cap, separators=(",", ":")) + "\n")
    return p


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
