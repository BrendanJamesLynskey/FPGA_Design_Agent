#!/usr/bin/env python3
"""Measure the product numbers of ``spec.yaml`` on the reference model (passband, alias rejection, SNR, full scale, latency).

    python3 showcase/pdm_decimator/model/product_numbers.py showcase/pdm_decimator/records/model_numbers_2026-11-14.json

A tone is turned into a second-order delta-sigma bit stream at 3.125 MHz, run through ``AudioChain``, and its level is read at the
(aliased) output frequency by a lock-in over the whole record. The SNR uses a coherent 1 kHz tone, a Hann window and the band 100 Hz to
15 kHz. Pure Python plus numpy; about 30 s.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from showcase.pdm_decimator.measure.pdm_measure import delta_sigma  # noqa: E402
from showcase.pdm_decimator.model import pdm_chain_ref as ref  # noqa: E402


def tone_level(f_hz: float, amp: float, seconds: float = 0.04) -> float:
    """Output level of a tone of amplitude ``amp`` relative to ``amp`` * full scale (lock-in at the aliased frequency)."""
    n = int(ref.FS_PDM * seconds)
    out = np.array(ref.process(delta_sigma(lambda k: amp * math.sin(2 * math.pi * f_hz * k / ref.FS_PDM), n))[0][8:], dtype=float)
    alias = f_hz % ref.FS_OUT
    alias = min(alias, ref.FS_OUT - alias)
    k = np.arange(len(out))
    z = abs(np.sum(out * np.exp(-2j * np.pi * alias / ref.FS_OUT * k))) * 2 / len(out)
    return float(z / (amp * 32768))


def numbers() -> dict:
    ref_level = tone_level(1000.0, 0.5)
    db = lambda f: 20 * math.log10(tone_level(f, 0.5) / ref_level)
    passband = {f"{f}": round(db(f), 2) for f in (200, 500, 2000, 5000, 8000, 12000, 15000)}
    alias_freqs = (40e3, 45e3, 52e3, 58e3, 62e3, 63.8e3, 100e3, 150e3, 190e3, 200e3, 300e3, 1e6)
    alias = {f"{f:.0f}": round(db(f), 1) for f in alias_freqs}
    npts = 2048
    fb = round(1000 / (ref.FS_OUT / npts))
    f0 = fb * ref.FS_OUT / npts
    bits = delta_sigma(lambda k: 0.5 * math.sin(2 * math.pi * f0 * k / ref.FS_PDM), (npts + 1000) * 64)
    out = np.array(ref.process(bits)[0][900:900 + npts], dtype=float)
    spec = np.abs(np.fft.rfft(out * np.hanning(npts))) ** 2
    fr = np.arange(len(spec)) * ref.FS_OUT / npts
    sig = spec[fb - 3:fb + 4].sum()
    snr = 10 * math.log10(sig / (spec[(fr >= 100) & (fr <= 15000)].sum() - sig))
    ones, sat_ones = ref.process([1] * 4000)
    zeros, sat_zeros = ref.process([0] * 4000)
    return {
        "source": "showcase/pdm_decimator/model/product_numbers.py on the reference model; second-order delta-sigma bits at 3.125 MHz",
        "output_rate_hz": ref.FS_OUT,
        "passband_db_relative_to_1khz": passband,
        "passband_worst_abs_db": max(abs(v) for v in passband.values()),
        "alias_db_relative_to_input": alias,
        "alias_worst_db": max(alias.values()),
        "snr_db_1khz_minus6dbfs_100hz_15khz": round(snr, 1),
        "full_scale_ones": {"saturates": sat_ones, "first_samples": ones[:6]},
        "full_scale_zeros": {"saturates": sat_zeros, "first_samples": zeros[:6]},
        "latency": {"pdm_samples_before_audio_sample_0": ref.FIRST_SAMPLE_AT, "microseconds": round(ref.FIRST_SAMPLE_AT / ref.FS_PDM * 1e6, 1)},
    }


if __name__ == "__main__":
    res = numbers()
    Path(sys.argv[1]).write_text(json.dumps(res, indent=1) + "\n")
    print(f"passband worst {res['passband_worst_abs_db']} dB, alias worst {res['alias_worst_db']} dB, SNR {res['snr_db_1khz_minus6dbfs_100hz_15khz']} dB")
