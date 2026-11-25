#!/usr/bin/env python3
"""Brief 162: DRIVE x SLEW x series R on a 50 ohm line of 1, 3, 6 and 10 inches with 5 pF, across the three IBIS corners.

    python3 tools/offchip_drive_slew_sweep.py [--out results/162_kr260_si]

Uses brief 155's solver (flow/offchip_model.py) on AMD's IBIS output models. One process, pure Python, about 15 minutes.
Writes drive_slew_sweep.csv; every row names the IBIS file, revision and model.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flow"))
import offchip_check as C       # noqa: E402

#: (label, family class, bank type, standard, drives, slews): the brief's three standards
SETS = [
    ("7-series HR", "7series", "HR", "LVCMOS33", (4, 8, 12, 16), ("SLOW", "FAST")),
    ("7-series HR", "7series", "HR", "LVCMOS25", (4, 8, 12, 16), ("SLOW", "FAST")),
    ("UltraScale+ HP", "ultrascale_plus", "HP", "LVCMOS18", (2, 4, 6, 8, 12), ("SLOW", "MEDIUM", "FAST")),
]
RS = (0, 10, 15, 22, 27, 33, 47)
LENGTHS = (1, 3, 6, 10)


def run(out: Path, z0: float = 50.0, c_pf: float = 5.0) -> None:
    rows = []
    for label, fc, bt, std, drives, slews in SETS:
        mf = C.model_family(fc, bt)
        lim = C.rx_limits(fc, bt)
        for ln in LENGTHS:
            for d in drives:
                for s in slews:
                    for rs in RS:
                        ev = C.evaluate_cached(mf, bt, std, d, s, rs, "none", z0, ln, c_pf, 3.2, (), None, None)
                        if "error" in ev:
                            continue
                        flags = C.judge(ev, lim, not ev["lumped"], 10.0)
                        rows.append({
                            "bank": label, "standard": std, "length_in": ln, "drive_ma": d, "slew": s, "series_ohm": rs,
                            "overshoot_over_vcco_v": round(ev["worst_over_vcco_v"], 3), "undershoot_under_gnd_v": round(ev["worst_under_gnd_v"], 3),
                            "first_incident_margin_v": None if ev["min_first_incident_margin_always_v"] is None else round(ev["min_first_incident_margin_always_v"], 3),
                            "ringback_margin_v": None if ev["min_ringback_margin_v"] is None else round(ev["min_ringback_margin_v"], 3),
                            "settle_ns": round(ev["max_settle_ns"], 2), "ring_pp_v": round(ev["max_ring_pp_v"], 3),
                            "rx_rise_2080_ns_weak": None if ev["rx_rise_2080_ns"]["min"] is None else round(ev["rx_rise_2080_ns"]["min"], 3),
                            "rx_rise_2080_ns_typ": None if ev["rx_rise_2080_ns"]["typ"] is None else round(ev["rx_rise_2080_ns"]["typ"], 3),
                            "rx_rise_2080_ns_strong": None if ev["rx_rise_2080_ns"]["max"] is None else round(ev["rx_rise_2080_ns"]["max"], 3),
                            "lumped": ev["lumped"], "flags": " ".join(sorted({f[0] for f in flags})), "pass": not flags,
                            "model": ev["source"]["model"], "ibis_file": ev["source"]["file"], "file_rev": ev["source"]["file_rev"]})
            print(f"  {label} {std} {ln} in", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "drive_slew_sweep.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "rows")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results/162_kr260_si"))
    run(Path(ap.parse_args().out))
