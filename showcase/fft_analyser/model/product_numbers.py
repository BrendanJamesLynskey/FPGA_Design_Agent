#!/usr/bin/env python3
"""Measure the product numbers of ``spec.yaml`` on the reference model: accuracy against a floating-point FFT, noise floor and SFDR at
N = 64, 256 and 1024, and the clock count of a run.

    python3 showcase/fft_analyser/model/product_numbers.py showcase/fft_analyser/records/model_numbers_2026-11-14.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from showcase.fft_analyser.model import fft_ref as ref  # noqa: E402


def tone(n: int, bin_: int, amp: float = 0.9) -> list[int]:
    return [round(amp * 32767 * math.sin(2 * math.pi * bin_ * i / n)) for i in range(n)]


def accuracy(n: int) -> dict:
    x = tone(n, 10 if n == 64 else 40)
    win = np.array(ref.window_table(1, n), dtype=float) / 32768
    float_fft = np.fft.fft(np.array(x, dtype=float) * win) / n
    fixed = np.array([complex(*c) for c in ref.fft_frame(ref.windowed(x, 1))])
    err = np.abs(fixed - float_fft)
    return {"n": n, "worst_component_error_lsb": round(float(max(np.abs(fixed.real - float_fft.real).max(), np.abs(fixed.imag - float_fft.imag).max())), 2),
            "rms_error_lsb": round(float(np.sqrt(np.mean(err ** 2) / 2)), 3), "peak_lsb": round(float(np.abs(float_fft).max()), 1)}


def sfdr(n: int, frames_log2: int = 3) -> float:
    rng = np.random.default_rng(3)
    k0 = 10 if n == 64 else 40
    base = tone(n, k0)
    # eight frames with 2 LSB of dither stand in for the clean-tone-plus-noise a converter would give
    frames = [[v + int(rng.integers(-2, 3)) for v in base] for _ in range(1 << frames_log2)]
    p = np.zeros(n // 2)
    for f in frames:
        p += np.array([ref.power(c) for c in ref.fft_frame(ref.windowed(f, 1))[: n // 2]], dtype=float) / len(frames)
    pk = int(p.argmax())
    mask = np.ones(n // 2, bool)
    mask[max(pk - 2, 0): pk + 3] = False
    return round(10 * math.log10(p[pk] / p[mask].max()), 1)


def numbers() -> dict:
    sizes = (64, 256, 1024)
    return {
        "source": "showcase/fft_analyser/model/product_numbers.py on the reference model (radix-2 scaled butterflies)",
        "accuracy_vs_float": [accuracy(n) for n in sizes],
        "sfdr_db_hann_8_frames_with_2lsb_dither": {str(n): sfdr(n) for n in sizes},
        "run_clocks": {str(n): {"K1_min": n, "K8_min": 8 * n, "pipeline_latency_samples": n - 1} for n in sizes},
    }


if __name__ == "__main__":
    res = numbers()
    Path(sys.argv[1]).write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({a["n"]: (a["worst_component_error_lsb"], a["rms_error_lsb"]) for a in res["accuracy_vs_float"]}), res["sfdr_db_hann_8_frames_with_2lsb_dither"])
