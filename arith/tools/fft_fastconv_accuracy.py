#!/usr/bin/env python3
"""Accuracy of the fast-convolution block against numpy.convolve of the unquantised taps (arith brief 161): worst and rms error in output LSB and the SQNR, per N and filter length, for a
low-pass, a random and a delta filter of absolute gain at most 0.9 * 2**GB and a random complex stream of 3 blocks. The RTL equals the model bit for bit (tests/test_fft_fastconv_*_rtl.py).

    python3 -m arith.tools.fft_fastconv_accuracy [--out PATH]      (writes arith/fft_fastconv/verif/results/accuracy.json)"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import random
from pathlib import Path

import numpy as np

from arith.fft_fastconv import model
from arith.tools import arith_common as ac

W, TW, WH, FH, GB = 16, 18, 24, 14, 1
SEED = 20261122


def taps(n: int, kind: str, rng: random.Random) -> list[float]:
    if kind == "lowpass":
        fc = 0.12
        h = [(math.sin(2 * math.pi * fc * (i - (n - 1) / 2)) / (math.pi * (i - (n - 1) / 2)) if i != (n - 1) / 2 else 2 * fc) * (0.54 - 0.46 * math.cos(2 * math.pi * i / max(1, n - 1))) for i in range(n)]
    elif kind == "random":
        h = [rng.uniform(-1, 1) / n for _ in range(n)]
    else:
        h = [0.0] * n
        h[n // 3] = 0.9
    g = sum(abs(v) for v in h)
    lim = (1 << GB) * 0.9
    return [v * min(1.0, lim / g) for v in h] if g > 0 else h


def point(logn: int, ll: int, kind: str) -> dict:
    p = dict(LOGN=logn, L=ll, W=W, TW=TW, WH=WH, FH=FH, GB=GB, RND=1)
    n = 1 << logn
    b = n - ll + 1
    rng = random.Random(SEED + logn * 1000 + ll)
    h = taps(ll, kind, rng)
    hq = model.filter_spectrum(h, n, WH, FH)
    a = int(0.5 * (1 << (W - 1)))
    x = [(rng.randrange(-a, a + 1), rng.randrange(-a, a + 1)) for _ in range(3 * b)]
    y, sat = model.process(p, hq, x)
    ref = np.convolve(np.array([u + 1j * v for u, v in x]), np.array(h))[:len(y)]
    yc = np.array([u + 1j * v for u, v in y])
    err = yc - ref
    worst = float(np.max(np.maximum(np.abs(err.real), np.abs(err.imag))))
    rms = float(np.sqrt(np.mean(np.abs(err) ** 2)))
    sqnr = float(10 * math.log10(np.sum(np.abs(ref) ** 2) / max(np.sum(np.abs(err) ** 2), 1e-30))) if np.sum(np.abs(ref) ** 2) > 0 else 999.0
    return {"LOGN": logn, "L": ll, "B": b, "kind": kind, "gain": round(sum(abs(v) for v in h), 3), "samples": len(y), "saturated": sat, "worst_lsb": round(worst, 3), "rms_lsb": round(rms, 3), "sqnr_db": round(sqnr, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ac.ARITH / "fft_fastconv" / "verif" / "results" / "accuracy.json"))
    a = ap.parse_args()
    pts = []
    for logn in (6, 8, 10, 12):
        n = 1 << logn
        for ll, kind in ((n // 8 + 1, "lowpass"), (n // 2 + 1, "random"), (3 * n // 4 + 1, "lowpass"), (n // 4 + 1, "delta")):
            pts.append(point(logn, ll, kind))
    res = {"what": "error of the bit-exact model (equal to the RTL) against numpy.convolve of the unquantised taps and the same samples, in output LSB (W = 16, TW = 18, WH = 24, FH = 14, GB = 1); a random complex stream of 3 blocks per point",
           "date": datetime.date.today().isoformat(), "numpy": np.__version__, "seed": SEED, "points": len(pts), "worst_lsb_max": max(p["worst_lsb"] for p in pts), "sqnr_db_min": min(p["sqnr_db"] for p in pts),
           "saturated_max": max(p["saturated"] for p in pts), "results": pts}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    print(f"{len(pts)} points; worst {res['worst_lsb_max']} LSB, SQNR >= {res['sqnr_db_min']} dB -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
