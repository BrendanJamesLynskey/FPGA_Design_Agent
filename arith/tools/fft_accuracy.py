#!/usr/bin/env python3
"""Accuracy of the FFT models against NumPy's double-precision FFT (arith brief 148): worst and rms error in units of the output LSB, SQNR for noise-like input and SFDR for a
full-scale tone, per variant, scaling mode, N and twiddle width. The RTL equals the models bit for bit (tests/test_fft_*_rtl.py), so these are the RTL's figures.

    python3 -m arith.tools.fft_accuracy [--out PATH]      (writes arith/fft/verif/results/accuracy.json)"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import random
from pathlib import Path

import numpy as np

from arith.fft_common import fft_ref as f
from arith.tools import arith_common as ac

W = 16
LOGNS = (3, 6, 8, 10, 12)
TWS = (12, 16, 18, 24)
SEED = 20261121


def point(variant: str, logn: int, tw: int, scale: int, rnd: int = 1) -> dict:
    n = 1 << logn
    rng = random.Random(SEED + logn * 100 + tw)
    fs = 1 << (W - 1)
    # noise-like frame: components uniform in +-0.65 FS (magnitude < 0.92 FS)
    x = [(rng.randrange(-int(0.65 * fs), int(0.65 * fs)), rng.randrange(-int(0.65 * fs), int(0.65 * fs))) for _ in range(n)]
    xc = np.array([a + 1j * b for a, b in x])
    y = f.fft_frame(variant, x, tw, scale, rnd, 0, 1)
    yc = np.array([a + 1j * b for a, b in y])
    ref = np.fft.fft(xc) / (n if scale else 1)
    err = yc - ref
    worst = float(np.max(np.maximum(np.abs(err.real), np.abs(err.imag))))
    rms = float(np.sqrt(np.mean(np.abs(err) ** 2)))
    sqnr = float(10 * math.log10(np.sum(np.abs(ref) ** 2) / np.sum(np.abs(err) ** 2)))
    # a full-scale coherent tone at a bin that is not a multiple of anything simple; SFDR is the tone's bin over the largest other bin
    k0 = (n // 5) | 1
    tone = f_quant(n, k0, 0.9 * fs)
    yt = np.array([a + 1j * b for a, b in f.fft_frame(variant, tone, tw, scale, rnd, 0, 1)])
    mag = np.abs(yt)
    other = np.max(np.delete(mag, k0))
    sfdr = float(20 * math.log10(mag[k0] / max(other, 1e-9)))
    return {"variant": variant, "LOGN": logn, "W": W, "TW": tw, "SCALE": scale, "RND": rnd, "worst_lsb": round(worst, 3), "rms_lsb": round(rms, 3), "sqnr_db": round(sqnr, 1), "sfdr_db": round(sfdr, 1)}


def f_quant(n: int, k: int, amp: float) -> list[tuple[int, int]]:
    return [(round(amp * math.cos(2 * math.pi * k * i / n)), round(amp * math.sin(2 * math.pi * k * i / n))) for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ac.ARITH / "fft" / "verif" / "results" / "accuracy.json"))
    a = ap.parse_args()
    pts = [point(v, ln, tw, sc) for v in ("sdf", "burst") for sc in (1, 0) for ln in LOGNS for tw in TWS]
    sc1 = [p["worst_lsb"] for p in pts if p["SCALE"] == 1]
    sc0 = [p["worst_lsb"] for p in pts if p["SCALE"] == 0]
    out = {"what": "error of the bit-exact models (equal to the RTL) against numpy.fft in units of the output LSB; noise-like input of components uniform in +-0.65 full scale; SFDR for a coherent tone of 0.9 full scale",
           "date": datetime.date.today().isoformat(), "numpy": np.__version__, "seed": SEED, "points": len(pts),
           "worst_lsb_scaled_max": max(sc1), "worst_lsb_unscaled_max": max(sc0),
           "sqnr_db_min_scaled": min(p["sqnr_db"] for p in pts if p["SCALE"] == 1), "sqnr_db_min_unscaled_tw16plus": min(p["sqnr_db"] for p in pts if p["SCALE"] == 0 and p["TW"] >= 16),
           "sfdr_db_min_tw16plus": min(p["sfdr_db"] for p in pts if p["TW"] >= 16), "results": pts}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(pts)} points; worst scaled {max(sc1)} LSB, worst unscaled {max(sc0)} LSB -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
