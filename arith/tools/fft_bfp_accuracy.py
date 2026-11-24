#!/usr/bin/env python3
"""Accuracy of the block-floating-point FFT against NumPy's double-precision FFT, beside the scaled and unscaled modes of arith/fft (arith brief 161).

For every N = 8 .. 4096, both architectures, and four input levels (noise-like frames of components uniform in +-A, A = 0.65 full scale, then 20, 40 and 60 dB lower) the bit-exact models of the three
modes are compared with numpy.fft of the same integer frame:
  scaled (SCALE = 1, W bit output, value = out * N), unscaled (SCALE = 0, W + LOGN bit output, value = out), block floating point (W bit output, value = out * 2**s).
Recorded per point and mode: the worst and rms error in units of that mode's output LSB (scaled: N units of the transform, unscaled: 1, BFP: 2**s) and the SQNR (signal energy over error
energy, mode independent); for the BFP mode also the exponent, the error bound (the unscaled core's measured worst error plus 2**s) and whether it holds.

    python3 -m arith.tools.fft_bfp_accuracy [--out PATH]      (writes arith/fft_bfp/verif/results/accuracy.json)"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import random
from pathlib import Path

import numpy as np

from arith.fft_bfp import model
from arith.fft_common import fft_ref as f
from arith.tools import arith_common as ac

W = 16
TW = 18
LOGNS = tuple(range(3, 13))
LEVELS_DB = (0, -20, -40, -60)
SEED = 20261122


def stats(y, ref, lsb):
    err = y - ref
    worst = float(np.max(np.maximum(np.abs(err.real), np.abs(err.imag))))
    rms = float(np.sqrt(np.mean(np.abs(err) ** 2)))
    sqnr = float(10 * math.log10(np.sum(np.abs(ref) ** 2) / max(np.sum(np.abs(err) ** 2), 1e-30)))
    return worst, rms, sqnr, worst / lsb, rms / lsb


def point(variant: str, logn: int, level_db: int) -> dict:
    n = 1 << logn
    rng = random.Random(SEED + logn * 1000 + abs(level_db))
    amp = max(1, round(0.65 * (1 << (W - 1)) * 10 ** (level_db / 20)))
    x = [(rng.randrange(-amp, amp + 1), rng.randrange(-amp, amp + 1)) for _ in range(n)]
    xc = np.array([a + 1j * b for a, b in x])
    ref = np.fft.fft(xc)
    out = {"variant": variant, "LOGN": logn, "W": W, "TW": TW, "level_db": level_db, "amp": amp}
    ys = np.array([a + 1j * b for a, b in f.fft_frame(variant, x, TW, 1, 1, 0, 1)]) * n
    w, r, s, wl, rl = stats(ys, ref, n)
    out["scaled"] = {"worst_lsb": round(wl, 3), "rms_lsb": round(rl, 3), "sqnr_db": round(s, 1)}
    core = f.fft_frame(variant, x, TW, 0, 1, 0, 1)
    yu = np.array([a + 1j * b for a, b in core])
    w, r, s, wl, rl = stats(yu, ref, 1)
    out["unscaled"] = {"worst_lsb": round(wl, 3), "rms_lsb": round(rl, 3), "sqnr_db": round(s, 1)}
    e_core = w
    words = model.frame(variant, {"TW": TW, "W": W, "RND": 1, "ORDER": 0}, x, 0)
    s_exp = words[0][2]
    yb = np.array([(a + 1j * b) * 2.0 ** s_exp for a, b, _ in words])
    w, r, s, wl, rl = stats(yb, ref, 2.0 ** s_exp)
    bound = e_core + 2.0 ** s_exp
    out["bfp"] = {"exp": s_exp, "worst_lsb": round(wl, 3), "rms_lsb": round(rl, 3), "sqnr_db": round(s, 1), "worst_abs": round(w, 3), "bound_abs": round(bound, 3), "within_bound": bool(w <= bound)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ac.ARITH / "fft_bfp" / "verif" / "results" / "accuracy.json"))
    a = ap.parse_args()
    pts = [point(v, ln, lv) for v in ("sdf", "burst") for ln in LOGNS for lv in LEVELS_DB]
    full = [p for p in pts if p["level_db"] == 0]
    quiet = [p for p in pts if p["level_db"] == -60]
    res = {"what": "error of the bit-exact models (equal to the RTL) against numpy.fft; noise-like input, components uniform in +-A, A = 0.65 full scale at level 0 dB; LSB = the mode's own output LSB "
                   "(scaled: one unit of the output word is N units of the transform; unscaled: 1; block floating point: 2**exponent); SQNR is mode independent",
           "date": datetime.date.today().isoformat(), "numpy": np.__version__, "seed": SEED, "W": W, "TW": TW, "points": len(pts),
           "all_within_bound": all(p["bfp"]["within_bound"] for p in pts),
           "bfp_worst_lsb_max_full_level": max(p["bfp"]["worst_lsb"] for p in full),
           "bfp_sqnr_db_min_full_level": min(p["bfp"]["sqnr_db"] for p in full), "unscaled_sqnr_db_min_full_level": min(p["unscaled"]["sqnr_db"] for p in full),
           "scaled_sqnr_db_min_full_level": min(p["scaled"]["sqnr_db"] for p in full), "bfp_sqnr_db_min_minus60": min(p["bfp"]["sqnr_db"] for p in quiet),
           "scaled_sqnr_db_min_minus60": min(p["scaled"]["sqnr_db"] for p in quiet), "results": pts}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    print(f"{len(pts)} points; within bound: {res['all_within_bound']}; BFP SQNR at 0 dB >= {res['bfp_sqnr_db_min_full_level']} dB, at -60 dB >= {res['bfp_sqnr_db_min_minus60']} dB -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
