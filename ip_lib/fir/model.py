"""Golden model for ip_lib/fir: plain Python written from the definition of a FIR filter, not from the RTL.

    y[n] = sum_{k=0}^{TAPS-1} h[k] * x[n-k], with x[n] = 0 before the first sample after reset; full precision.

Every variant (dsp_bram, dist_ram, serial, lut_mult) must match `fir` exactly. `fir_timing` gives the latency and
initiation interval each variant declares in its RTL localparams (LATENCY, II); the tests measure both in simulation.
"""
from __future__ import annotations

import math

IMPLS = ("dsp_bram", "dist_ram", "serial", "lut_mult")


def acc_width(taps: int, data_w: int, coef_w: int) -> int:
    return data_w + coef_w + math.ceil(math.log2(taps))


def fir(xs: list[int], h: list[int], history: list[int] | None = None) -> list[int]:
    """Outputs for samples xs with coefficients h. `history` (most recent last) is the state before xs; zeros if None."""
    hist = list(history or [])
    out = []
    for x in xs:
        hist.append(x)
        out.append(sum(c * hist[-1 - k] for k, c in enumerate(h) if k < len(hist)))
    return out


def fir_segments(segments: list[tuple[list[int], list[int]]]) -> list[int]:
    """Several coefficient sets in turn, the history carried across: [(h, xs), ...] -> all outputs."""
    out, hist = [], []
    for h, xs in segments:
        out += fir(xs, h, hist)
        hist += xs
    return out


def fir_timing(impl: str, taps: int, fold: int = 4) -> dict:
    """Latency (clocks from the accepting clock to m_valid) and initiation interval of a variant, as its RTL declares."""
    if impl not in IMPLS:
        raise ValueError(f"unknown FIR variant {impl}")
    if impl == "lut_mult":
        return {"latency": 2 + math.ceil(math.log2(taps)), "ii": 1, "macs": taps}
    f = taps if impl == "serial" else fold
    macs = math.ceil(taps / f)
    tree = math.ceil(math.log2(macs)) if macs > 1 else 0
    return {"latency": f + 8 + tree, "ii": f + 3, "macs": macs}
