#!/usr/bin/env python3
"""The brief 155 study runs: output resistance of every LVCMOS driver, the termination matrix on a 50 ohm line, the best DRIVE and series R.

    python3 tools/offchip_study.py [--out results/155_offchip] [--length-in 10] [--c-pf 5] [--only r_out|dci|matrix|best|length]

Every number comes from ``flow/offchip_model.py`` run on AMD's IBIS output models (flow/offchip_data/driver_models.json; source file,
revision and model name are in each CSV row). One process, pure Python, a few minutes.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flow"))
import offchip_check as C       # noqa: E402
import offchip_model as M       # noqa: E402

#: (label, family class, bank type, standard, drives, slews)
SETS = [
    ("7-series HR", "7series", "HR", "LVCMOS33", (4, 8, 12, 16), ("SLOW", "FAST")),
    ("7-series HR", "7series", "HR", "LVCMOS25", (4, 8, 12, 16), ("SLOW", "FAST")),
    ("7-series HR", "7series", "HR", "LVCMOS18", (4, 8, 12, 16, 24), ("SLOW", "FAST")),
    ("UltraScale+ HD", "ultrascale_plus", "HD", "LVCMOS33", (4, 8, 12, 16), ("SLOW", "FAST")),
    ("UltraScale+ HP", "ultrascale_plus", "HP", "LVCMOS18", (2, 4, 6, 8, 12), ("SLOW", "MEDIUM", "FAST")),
]
TERM_ORDER = ["none", "series_10", "series_15", "series_22", "series_33", "series_47", "parallel_gnd", "parallel_vtt", "thevenin", "ac"]


def combos():
    for label, fc, bt, std, drives, slews in SETS:
        for d in drives:
            for s in slews:
                yield label, fc, bt, std, d, s


def r_out(out: Path, z0: float) -> None:
    rows = []
    for label, fc, bt, std, d, s in combos():
        mf = C.model_family(fc, bt)
        key = M.model_key(mf, std, d, s, bt if mf != "artix7" else "")
        if key is None:
            continue
        src = M.source_for(key)
        for c in M.CORNERS:
            drv = M.get_driver(key, c)
            r0 = M.r_launch(drv, z0)
            r22 = M.r_launch(drv, z0 + 22.0)
            rows.append({"bank": label, "standard": std, "drive_ma": d, "slew": s, "corner": c, "vcco_v": drv.vcc,
                         "r_pu_ohm_into_z0": round(r0["r_pu"], 1), "r_pd_ohm_into_z0": round(r0["r_pd"], 1),
                         "r_pu_ohm_into_z0_plus_22": round(r22["r_pu"], 1), "r_pd_ohm_into_z0_plus_22": round(r22["r_pd"], 1),
                         "r_rail_pu_ohm": round(r0["r_rail_pu"], 1), "r_rail_pd_ohm": round(r0["r_rail_pd"], 1),
                         "r_small_pu_ohm": round(r0["r_small_pu"], 1), "r_small_pd_ohm": round(r0["r_small_pd"], 1),
                         "i_pu_max_ma": round(r0["i_sat_pu"] * 1e3, 1), "i_pd_max_ma": round(r0["i_sat_pd"] * 1e3, 1),
                         "t2080_rise_ns": round(drv.t2080_r * 1e9, 3), "t2080_fall_ns": round(drv.t2080_f * 1e9, 3),
                         "c_comp_pf": round(drv.c_comp * 1e12, 2), "vinl_v": drv.vinl, "vinh_v": drv.vinh,
                         "ibis_file": src["file"], "ibis_ver": src["ibis_ver"], "file_rev": src["file_rev"], "model": src["model"]})
    _csv(out / "r_out.csv", rows)


def dci(out: Path) -> None:
    rows = []
    lib = M.library()["models"]
    for k in sorted(lib):
        if "_DCI_" not in k or not k.endswith(("OUT40", "OUT48", "OUT60")):
            continue
        for c in M.CORNERS:
            d = M.get_driver(k, c)
            r = M.r_mid(d)
            src = M.source_for(k)
            rows.append({"model": src["model"], "corner": c, "vcco_v": d.vcc, "r_pu_mid_ohm": round(r["r_pu"], 1), "r_pd_mid_ohm": round(r["r_pd"], 1),
                         "ibis_file": src["file"], "ibis_ver": src["ibis_ver"], "file_rev": src["file_rev"]})
    _csv(out / "dci_outputs.csv", rows)


def matrix(out: Path, z0: float, length: float, c_pf: float, only: str | None = None) -> None:
    rows = []
    for label, fc, bt, std, d, s in combos():
        mf = C.model_family(fc, bt)
        lim = C.rx_limits(fc, bt)
        for term in TERM_ORDER:
            rs, _ = C.TERMS[term]
            ev = C.evaluate_cached(mf, bt, std, d, s, rs, term if not term.startswith("series") else "none", z0, length, c_pf, 3.2, (), None, None)
            if "error" in ev:
                continue
            for c in M.CORNERS:
                cc = ev["corners"][c]
                rise, fall = cc["rise"], cc["fall"]
                rows.append({"bank": label, "standard": std, "drive_ma": d, "slew": s, "termination": term, "series_ohm": rs, "corner": c,
                             "vcco_v": cc["vcc"], "r_pu_ohm": round(cc["r_pu"], 1), "r_pd_ohm": round(cc["r_pd"], 1),
                             "overshoot_above_vcco_v": round(rise["over_vcco_v"], 3), "undershoot_below_gnd_v": round(fall["under_gnd_v"], 3),
                             "first_incident_rise_margin_v": _r(rise["first_incident_margin_always_v"]),
                             "first_incident_fall_margin_v": _r(fall["first_incident_margin_always_v"]),
                             "staircase_visible": (not rise["lumped"]) or (not fall["lumped"]),
                             "ringback_rise_margin_v": _r(rise["ringback_margin_v"]), "ringback_fall_margin_v": _r(fall["ringback_margin_v"]),
                             "settle_rise_ns": round(rise["settle_ns"], 2), "settle_fall_ns": round(fall["settle_ns"], 2),
                             "rx_rise_2080_ns": _r(rise["rise_2080_ns"]), "rx_fall_2080_ns": _r(fall["rise_2080_ns"]),
                             "t_over_roc_ns": round(max(rise["t_over_roc_ns"], fall["t_over_roc_ns"]), 2),
                             "t_under_roc_ns": round(max(rise["t_under_roc_ns"], fall["t_under_roc_ns"]), 2),
                             "z0_ohm": z0, "length_in": length, "c_load_pf": c_pf, "er_eff": 3.2,
                             "ibis_file": ev["source"]["file"], "ibis_ver": ev["source"]["ibis_ver"], "file_rev": ev["source"]["file_rev"], "model": ev["source"]["model"]})
        print(f"  matrix: {label} {std} {d} mA {s}", flush=True)
    _csv(out / "termination_matrix.csv", rows)


def _r(x, n=3):
    return None if x is None else round(x, n)


def _csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{path} ({len(rows)} rows)")


def best(out: Path, z0: float, length: float, c_pf: float) -> None:
    """For each standard: every (DRIVE, SLEW, series R in the E-series set), judged at all corners; the best by balanced priority and by edge rate."""
    out_rows = []
    for label, fc, bt, std, drives, slews in SETS:
        mf = C.model_family(fc, bt)
        lim = C.rx_limits(fc, bt)
        for d in drives:
            for s in slews:
                for rs in C.E_SERIES_RS:
                    ev = C.evaluate_cached(mf, bt, std, d, s, rs, "none", z0, length, c_pf, 3.2, (), None, None)
                    if "error" in ev:
                        continue
                    flags = C.judge(ev, lim, not ev["lumped"], 10.0)
                    typ = ev["corners"]["typ"]
                    ok = not flags and (ev["min_first_incident_margin_always_v"] >= 0.0)
                    out_rows.append({"bank": label, "standard": std, "drive_ma": d, "slew": s, "series_ohm": rs, "pass": ok, "flags": " ".join(sorted({f[0] for f in flags})),
                                     "r_pu_typ": round(typ["r_pu"], 1), "r_pd_typ": round(typ["r_pd"], 1),
                                     "r_pu_weak": round(ev["corners"]["min"]["r_pu"], 1), "r_pd_weak": round(ev["corners"]["min"]["r_pd"], 1),
                                     "r_pu_strong": round(ev["corners"]["max"]["r_pu"], 1), "r_pd_strong": round(ev["corners"]["max"]["r_pd"], 1),
                                     "total_pu_typ": round(typ["r_pu"] + rs, 1), "total_pd_typ": round(typ["r_pd"] + rs, 1),
                                     "mismatch_worst_corner_pct": round(100 * C._mismatch(ev), 1),
                                     "worst_overshoot_v": round(ev["worst_over_vcco_v"], 3), "worst_undershoot_v": round(ev["worst_under_gnd_v"], 3),
                                     "first_incident_margin_v": round(ev["min_first_incident_margin_always_v"], 3),
                                     "ringback_margin_v": _r(ev["min_ringback_margin_v"]),
                                     "settle_ns": round(ev["max_settle_ns"], 2), "rx_rise_2080_ns_weak": _r(ev["rx_rise_2080_ns"]["min"]),
                                     "rx_rise_2080_ns_strong": _r(ev["rx_rise_2080_ns"]["max"]),
                                     "model": ev["source"]["model"], "ibis_file": ev["source"]["file"], "file_rev": ev["source"]["file_rev"]})
        print(f"  best: {label} {std}", flush=True)
    _csv(out / "series_r_sweep.csv", out_rows)


def winners(out: Path, ui_ns: float = 10.0) -> None:
    """Judge every row of series_r_sweep.csv with the check's own criteria and list the best per standard.

    A row passes when it has no ``OFFCHIP-*`` flag, a first-incident margin of at least ``FIRST_WAVE_GUARD_V`` at every corner (the sweep's
    margin is the one a staircase would dwell at, whatever the line length) and a weak-corner receiver 20-80 % time within
    ``RISE_FRACTION_OF_UI`` of the unit interval."""
    rows = list(csv.DictReader((out / "series_r_sweep.csv").open()))
    limit_rise = C.RISE_FRACTION_OF_UI * ui_ns
    win = {}
    for label, fc, bt, std, drives, slews in SETS:
        sel = []
        for r in rows:
            if r["standard"] != std or r["bank"] != label:
                continue
            ok = (not r["flags"] and float(r["first_incident_margin_v"]) >= C.FIRST_WAVE_GUARD_V and float(r["rx_rise_2080_ns_weak"]) <= limit_rise)
            r = dict(r, passes=ok)
            for k in ("series_ohm", "r_pu_typ", "r_pd_typ", "r_pu_weak", "r_pd_weak", "r_pu_strong", "r_pd_strong", "total_pu_typ", "total_pd_typ", "mismatch_worst_corner_pct",
                      "worst_overshoot_v", "first_incident_margin_v", "rx_rise_2080_ns_weak", "rx_rise_2080_ns_strong", "settle_ns"):
                r[k] = float(r[k])
            r["drive_ma"] = int(r["drive_ma"])
            sel.append(r)
        ok = [r for r in sel if r["passes"]]
        key = f"{label} {std}"
        ok.sort(key=lambda r: (r["mismatch_worst_corner_pct"], r["series_ohm"] > 0, r["drive_ma"]))
        win[key] = {"n_total": len(sel), "n_passing": len(ok), "best_by_match": ok[:3],
                    "best_edge_rate": sorted(ok, key=lambda r: r["rx_rise_2080_ns_weak"])[:3],
                    "best_emi": sorted(ok, key=lambda r: -r["rx_rise_2080_ns_strong"])[:3],
                    "criteria": {"first_wave_guard_v": C.FIRST_WAVE_GUARD_V, "max_weak_rise_ns": limit_rise, "ui_ns": ui_ns},
                    "pass_grid": {f"{r['drive_ma']} mA {r['slew']}": {} for r in sel}}
        for r in sel:
            win[key]["pass_grid"][f"{r['drive_ma']} mA {r['slew']}"][f"{r['series_ohm']:g}"] = "pass" if r["passes"] else (r["flags"] or "FIRST/RISE")
    (out / "best_match.json").write_text(json.dumps(win, indent=1))
    print(out / "best_match.json")


def fixed_series(out: Path, z0: float, length: float, c_pf: float) -> None:
    """The proposal when a series resistor is already on the board (22, 33, 47 ohm): which DRIVE and SLEW pass, per standard, or why none does."""
    res = {}
    for label, fc, bt, std, drives, slews in SETS:
        for rs in (22.0, 33.0, 47.0):
            g = {"name": f"{std}_{rs:g}", "ports": ["x"], "iostandard": std, "line": {"z0_ohm": z0, "length_in": length}, "load": {"c_pf": c_pf},
                 "external": {"series_ohm": rs}, "priority": "balanced", "ui_ns": 10.0}
            p = C.propose(g, fc, bt, max_sims=40)
            res[f"{label} {std} + {rs:g} ohm"] = {"passing": [{k: r[k] for k in ("drive", "slew", "worst_over_v", "worst_under_v", "first_incident_margin_v", "ringback_margin_v", "settle_ns", "rx_rise_2080_ns")}
                                                                for r in p["all_passing"]],
                                                   "best": None if p["best"] is None else {k: p["best"][k] for k in ("drive", "slew")}, "reason": p["reason"],
                                                   "n_simulated": len(p["simulated"]),
                                                   "failed": [{"drive": r["drive"], "slew": r["slew"], "flags": r["flags"], "worst_over_v": r["worst_over_v"], "worst_under_v": r["worst_under_v"],
                                                               "first_incident_margin_v": r["first_incident_margin_v"]} for r in p["simulated"] if not r["pass"]]}
        print(f"  fixed series: {label} {std}", flush=True)
    (out / "proposals_fixed_series.json").write_text(json.dumps(res, indent=1))
    print(out / "proposals_fixed_series.json")


def length_sweep(out: Path, z0: float, c_pf: float) -> None:
    rows = []
    cases = [("7-series HR", "7series", "HR", "LVCMOS33", 12, "SLOW", 22.0), ("7-series HR", "7series", "HR", "LVCMOS33", 12, "FAST", 22.0),
             ("7-series HR", "7series", "HR", "LVCMOS33", 8, "FAST", 33.0), ("7-series HR", "7series", "HR", "LVCMOS33", 16, "FAST", 0.0),
             ("7-series HR", "7series", "HR", "LVCMOS33", 12, "FAST", 0.0), ("7-series HR", "7series", "HR", "LVCMOS33", 4, "FAST", 0.0)]
    for label, fc, bt, std, d, s, rs in cases:
        mf = C.model_family(fc, bt)
        for length in (1.0, 3.0, 6.0, 10.0, 15.0):
            ev = C.evaluate_cached(mf, bt, std, d, s, rs, "none", z0, length, c_pf, 3.2, (), None, None)
            rows.append({"standard": std, "drive_ma": d, "slew": s, "series_ohm": rs, "length_in": length, "delay_ns": round(M.Line(z0, length).delay_s * 1e9, 3),
                         "worst_overshoot_v": round(ev["worst_over_vcco_v"], 3), "worst_undershoot_v": round(ev["worst_under_gnd_v"], 3),
                         "first_incident_margin_v": round(ev["min_first_incident_margin_always_v"], 3), "staircase_visible": not ev["lumped"],
                         "ringback_margin_v": _r(ev["min_ringback_margin_v"]), "settle_ns": round(ev["max_settle_ns"], 2),
                         "rx_rise_2080_ns_weak": _r(ev["rx_rise_2080_ns"]["min"]), "model": ev["source"]["model"]})
    _csv(out / "length_sweep.csv", rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "results/155_offchip"))
    ap.add_argument("--length-in", type=float, default=10.0)
    ap.add_argument("--c-pf", type=float, default=5.0)
    ap.add_argument("--z0", type=float, default=50.0)
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    todo = a.only.split(",") if a.only else ["r_out", "dci", "length", "best", "winners", "fixed", "matrix"]
    if "r_out" in todo:
        r_out(out, a.z0)
    if "dci" in todo:
        dci(out)
    if "length" in todo:
        length_sweep(out, a.z0, a.c_pf)
    if "best" in todo:
        best(out, a.z0, a.length_in, a.c_pf)
    if "fixed" in todo:
        fixed_series(out, a.z0, a.length_in, a.c_pf)
    if "winners" in todo:
        winners(out)
    if "matrix" in todo:
        matrix(out, a.z0, a.length_in, a.c_pf)
    (out / "study_parameters.json").write_text(json.dumps({"z0_ohm": a.z0, "length_in": a.length_in, "c_load_pf": a.c_pf, "er_eff": 3.2,
                                                           "line": "lossless", "model": "flow/offchip_model.py", "library": "flow/offchip_data/driver_models.json"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
