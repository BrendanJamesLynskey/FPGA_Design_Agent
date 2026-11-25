#!/usr/bin/env python3
"""Independent check of the driver model against the waveforms inside AMD's IBIS files (brief 155).

    python3 tools/ibis_fixture_check.py [--root /opt/Xilinx/2025.2/data/parts/xilinx] [--out results/155_offchip/ibis_fixture_check.json]

The model's switching ramp is calibrated to the IBIS 20-80 % *time* only (``flow/offchip_model.py``). The IBIS ``[Rising Waveform]`` table with the
50 ohm (25 ohm for the 4 mA models) fixture to ground holds the whole waveform of the same model, which the calibration did not see: its final level (set by the V-I curves and the
fixture) and its shape. This script simulates the driver into that fixture, aligns the two waveforms at their 50 % crossing and reports the error of the final
level and the rms and peak difference over the edge, as a share of the final level, at each corner. The IBIS files are read from the local install and not committed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flow"))
sys.path.insert(0, str(ROOT / "tools"))
import ibis_extract as X   # noqa: E402
import offchip_model as M  # noqa: E402

MODELS = ["artix7:LVCMOS33_F_8_HR", "artix7:LVCMOS33_S_8_HR", "artix7:LVCMOS33_F_16_HR", "artix7:LVCMOS33_S_4_HR", "artix7:LVCMOS18_F_12_HR",
          "zynquplus:HD_LVCMOS33_F_12", "zynquplus:HP_LVCMOS18_F_12", "zynquplus:HP_LVCMOS18_S_6"]


def waveform(lines: list[str], r_fix: float, v_fix: float, kind: str) -> list[list[float]]:
    """[t, typ, min, max] rows of the [Rising/Falling Waveform] section with that fixture."""
    for i, ln in enumerate(lines):
        if not ln.lower().startswith(f"[{kind.lower()} waveform]"):
            continue
        rf = vf = None
        rows: list[list[float]] = []
        for l2 in lines[i + 1:]:
            if l2.startswith("["):
                break
            t = l2.replace(" ", "")
            low = t.lower()
            if low.startswith("r_fixture="):
                rf = X.num(t.split("=", 1)[1])
            elif low.startswith("v_fixture=") and not low.startswith("v_fixture_m"):
                vf = X.num(t.split("=", 1)[1])
            elif l2.strip() and not l2.lstrip().startswith("|") and "=" not in l2:
                f = l2.split()
                if len(f) >= 4:
                    try:
                        rows.append([X.num(x) for x in f[:4]])
                    except ValueError:
                        pass
        if rf is not None and vf is not None and abs(rf - r_fix) < 1e-6 and abs(vf - v_fix) < 1e-6:
            return rows
    return []


def interp(t: list[float], v: list[float], x: float) -> float:
    if x <= t[0]:
        return v[0]
    if x >= t[-1]:
        return v[-1]
    for k in range(1, len(t)):
        if t[k] >= x:
            return v[k - 1] + (v[k] - v[k - 1]) * (x - t[k - 1]) / (t[k] - t[k - 1])
    return v[-1]


def cross(t, v, level):
    for k in range(1, len(v)):
        if v[k - 1] < level <= v[k]:
            return t[k - 1] + (level - v[k - 1]) / (v[k] - v[k - 1]) * (t[k] - t[k - 1])
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(X.DEFAULT_ROOT))
    ap.add_argument("--out", default=str(ROOT / "results/155_offchip/ibis_fixture_check.json"))
    a = ap.parse_args()
    texts = {k: Path(a.root, p).read_text(errors="replace") for k, p in X.FILES.items()}
    models = {k: X.split_models(t) for k, t in texts.items()}
    out = {"_note": "simulated driver into the IBIS 50 ohm-to-ground fixture against the IBIS [Rising Waveform]; error as a share of the IBIS final level",
           "sources": {k: X.header(texts[k][:4000]) for k in texts}, "models": {}}
    for key in MODELS:
        fam, name = key.split(":", 1)
        lines = models[fam][name]
        w, r_fix = [], 50.0
        for r_fix in (50.0, 25.0):                 # the fixture resistor of the model's waveforms (the 4 mA models use 25 ohm)
            w = waveform(lines, r_fix, 0.0, "Rising")
            if w:
                break
        if not w:
            out["models"][key] = {"error": "no 50 ohm to ground rising waveform"}
            continue
        res = {}
        for c, col in zip(M.CORNERS, (1, 2, 3)):
            t = [r[0] for r in w]
            v = [r[col] for r in w]
            vfin = v[-1]
            t50 = cross(t, v, 0.5 * vfin)
            drv = M.get_driver(key, c)
            tr = drv.ramp("r")
            dt = max(tr / 200, 1e-12)
            n = int(max(8 * tr, 6e-9) / dt)
            sim = M._fixture_wave(drv, "r", tr, dt, n, r_fix)
            ts = [i * dt for i in range(len(sim))]
            s50 = cross(ts, sim, 0.5 * sim[-1])
            win = [x for x in t if t50 - 1.0e-9 <= x <= t50 + 3.0e-9]
            errs = [(interp(ts, sim, (x - t50) + s50) - interp(t, v, x)) / vfin for x in win]
            res[c] = {"fixture_ohm": r_fix, "ibis_final_v": round(vfin, 4), "model_final_v": round(sim[-1], 4), "final_error_pct": round(100 * (sim[-1] - vfin) / vfin, 2),
                      "rms_error_pct_of_final": round(100 * (sum(e * e for e in errs) / len(errs)) ** 0.5, 2),
                      "peak_error_pct_of_final": round(100 * max(abs(e) for e in errs), 2), "points": len(win)}
        out["models"][key] = res
        print(key, {c: (r["final_error_pct"], r["rms_error_pct_of_final"], r["peak_error_pct_of_final"]) for c, r in res.items()})
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
