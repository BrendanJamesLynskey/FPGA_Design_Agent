"""CIC design from a plain spec (brief 19, adapter 2: the design tool). Pure numpy.

A decimating CIC (Hogenauer): N integrators at the input rate, a decimator by R, N combs with differential delay M.
Magnitude |H(f)| = |sin(pi f M R / fs_in) / (M R sin(pi f / fs_in))|^N (DC gain normalised to 1); the unnormalised
gain is (R M)^N and full-precision growth is ceil(N log2(R M)) bits (PG140 ch. 3, from Hogenauer 1981).

Given the input rate, rate change, pass band and the alias rejection wanted at the first alias band edge (the worst
place aliasing lands: fs_out - f_pass folds onto f_pass), choose the fewest stages in 3..6 (the core's limits).
"""
from __future__ import annotations

import math

import numpy as np


def cic_mag(f, fs_in, R, M, N):
    f = np.asarray(f, dtype=float)
    x = np.pi * f / fs_in
    with np.errstate(divide="ignore", invalid="ignore"):
        h = np.where(np.abs(np.sin(x)) < 1e-12, 1.0, np.sin(x * M * R) / (M * R * np.sin(x)))
    return np.abs(h) ** N


def cic_db(f, fs_in, R, M, N):
    return 20 * np.log10(np.maximum(cic_mag(f, fs_in, R, M, N), 1e-30))


def alias_rejection_db(fs_in, R, M, N, f_pass, n_points=400):
    """Attenuation (dB, positive) of the weakest point of the first alias band [fs_out - f_pass, fs_out + f_pass]."""
    fs_out = fs_in / R
    f = np.linspace(fs_out - f_pass, fs_out + f_pass, n_points)
    return float(-np.max(cic_db(f, fs_in, R, M, N)))


def design(spec):
    fs_in, R = spec["fs_in_hz"], spec["decimation"]
    M = spec.get("diff_delay", 1)
    fp = spec["passband_hz"]
    need = spec["alias_atten_db"]
    in_w = spec.get("input_width", 2)
    rows = []
    chosen = None
    for N in range(3, 7):
        row = {"stages": N,
               "alias_rejection_db": alias_rejection_db(fs_in, R, M, N, fp),
               "droop_at_passband_edge_db": float(cic_db(fp, fs_in, R, M, N)),
               "bit_growth": math.ceil(N * math.log2(R * M)),
               "gain": (R * M) ** N}
        rows.append(row)
        if chosen is None and row["alias_rejection_db"] >= need:
            chosen = row
    if chosen is None:
        raise ValueError("no stage count in 3..6 meets the alias rejection")
    N = chosen["stages"]
    return {"stages": N, "diff_delay": M, "rate": R, "input_width": in_w,
            "full_precision_width": in_w + chosen["bit_growth"], "gain": chosen["gain"],
            "gain_db": 20 * math.log10(chosen["gain"]),
            "alias_rejection_db": chosen["alias_rejection_db"],
            "droop_at_passband_edge_db": chosen["droop_at_passband_edge_db"],
            "fs_out_hz": fs_in / R, "candidates": rows,
            "summary": {k: chosen[k] for k in ("alias_rejection_db", "droop_at_passband_edge_db", "bit_growth", "gain")}
                       | {"stages": N, "diff_delay": M, "rate": R, "input_width": in_w, "fs_out_hz": fs_in / R,
                          "full_precision_width": in_w + chosen["bit_growth"], "candidates": rows}}


def impulse_response(R, M, N):
    """The equivalent FIR of the integrator-comb cascade (before decimation): a length-RM box convolved N times."""
    h = np.ones(1, dtype=np.int64)
    box = np.ones(R * M, dtype=np.int64)
    for _ in range(N):
        h = np.convolve(h, box)
    return h


def golden(x, R, M, N):
    """Exact integer model, zero initial state: filter, then keep every R-th output (all R phases are returned by the
    caller choosing `[ph::R]`). Full-precision core output equals this exactly."""
    x = np.asarray(x, dtype=np.int64)
    return np.convolve(x, impulse_response(R, M, N))[: len(x)]
