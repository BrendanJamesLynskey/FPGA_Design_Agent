"""FIR design from a plain spec (brief 19, adapter 1: the design tool).

spec (plain numbers) -> scipy.signal design (remez, kaiser window, least squares) -> smallest filter that meets the
spec in floating point -> integer coefficients at the chosen width -> the quantised response re-checked against the
spec (the attenuation lost to quantisation is reported) -> `.coe` text for the FIR Compiler.

Needs numpy and scipy (BSD-3). Pure functions, no Vivado.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

N_FREQ_PB = 4000
N_FREQ_SB = 16000


def _db(h, f, fs):
    _, H = signal.freqz(h, worN=f, fs=fs)
    return 20 * np.log10(np.abs(H) + 1e-30)


def comp_db(spec):
    """The droop the FIR must undo, as a function f -> dB (zero without a `compensation` block). Used when the FIR
    follows a CIC: the pass-band ripple is then measured on FIR x CIC, the flatness the user sees."""
    c = spec.get("compensation")
    if not c:
        return None
    from . import cic_design
    return lambda f: cic_design.cic_db(f, c["cic_fs_in_hz"], c["rate"], c.get("diff_delay", 1), c["stages"])


def response_metrics(h, fs, fpass, fstop, extra_db=None):
    """Passband ripple (max |gain| deviation from the DC-normalised gain, dB) and stopband attenuation (dB, positive)
    of coefficient vector `h` (any scale: normalised by its DC gain). `extra_db(f)` adds another stage's response in
    the pass band (a CIC ahead of this filter)."""
    h = np.asarray(h, dtype=float)
    h = h / np.sum(h)
    fpb = np.linspace(0, fpass, N_FREQ_PB)
    fsb = np.linspace(fstop, fs / 2, N_FREQ_SB)
    pb = _db(h, fpb, fs)
    if extra_db is not None:
        pb = pb + extra_db(fpb)
    return {
        "passband_ripple_db": float(np.max(np.abs(pb))),
        "stopband_atten_db": float(-np.max(_db(h, fsb, fs))),
    }


def _meets(h, spec, atten):
    m = response_metrics(h, spec["fs_in_hz"], spec["pass_edge_hz"], spec["stop_edge_hz"], comp_db(spec))
    return m["passband_ripple_db"] <= spec["ripple_db"] and m["stopband_atten_db"] >= atten, m


def _candidate(method, n, spec, atten, wsb=30.0):
    fs, fp, fst = spec["fs_in_hz"], spec["pass_edge_hz"], spec["stop_edge_hz"]
    if method == "remez":
        dp = 10 ** (spec["ripple_db"] / 20) - 1
        ds = 10 ** (-atten / 20)
        return signal.remez(n, [0, fp, fst, fs / 2], [1, 0], weight=[1 / dp, 1 / ds], fs=fs, maxiter=100)
    if method == "kaiser":
        beta = signal.kaiser_beta(atten + 1)
        return signal.firwin(n, (fp + fst) / 2, window=("kaiser", beta), fs=fs)
    if method == "firls":
        extra = comp_db(spec)
        if extra is None:
            return signal.firls(n, [0, fp, fst, fs / 2], [1, 1, 0, 0], weight=[1, 10 ** ((atten - 40) / 40)], fs=fs)
        # compensating filter: the wanted pass-band gain is 1 / (CIC response), piecewise linear on a fine grid
        grid = np.linspace(0, fp, 41)
        gains = 10 ** (-extra(grid) / 20)
        bands, des = [], []
        for a, b, ga, gb in zip(grid[:-1], grid[1:], gains[:-1], gains[1:]):
            bands += [a, b]
            des += [ga, gb]
        w = [1.0] * (len(bands) // 2) + [wsb]
        return signal.firls(n, bands + [fst, fs / 2], des + [0, 0], weight=w, fs=fs)
    raise ValueError(method)


def design_float(spec, methods=("remez", "kaiser", "firls"), max_taps=511):
    """Smallest odd-length filter per method that meets the spec (plus design_margin_db) in floating point.
    Returns the list of attempts and the chosen one (fewest taps; first method wins ties)."""
    atten = spec["atten_db"] + spec.get("design_margin_db", 0.0)
    out = []
    for m in methods:
        found = None
        weights = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0) if (m == "firls" and spec.get("compensation")) else (30.0,)
        if m != "firls" and spec.get("compensation"):
            out.append({"method": m, "taps": None, "note": "no arbitrary pass-band shape"})
            continue
        for n in range(spec.get("min_taps", 21), max_taps + 1, 2):
            for wsb in weights:
                try:
                    h = _candidate(m, n, spec, atten, wsb)
                except Exception:
                    continue
                if not np.all(np.isfinite(h)) or abs(np.sum(h)) < 1e-9:
                    continue
                ok, met = _meets(h, spec, atten)
                if ok:
                    found = {"method": m, "taps": n, "h": h / np.sum(h), **met}
                    break
            if found:
                break
        out.append(found or {"method": m, "taps": None})
    ok = [c for c in out if c["taps"]]
    if not ok:
        raise ValueError("no method met the spec within max_taps")
    return out, min(ok, key=lambda c: c["taps"])


def quantise(h, width, gain=1.0):
    """Scale so the largest coefficient fills a signed `width`-bit word, round to nearest. Returns (ints, scale)."""
    h = np.asarray(h, dtype=float) * gain
    full = 2 ** (width - 1) - 1
    scale = full / np.max(np.abs(h))
    return np.rint(h * scale).astype(np.int64), scale


def design(spec):
    """The whole design step. Returns a dict (JSON-safe except `h_float`/`coef`, which are arrays)."""
    cands, best = design_float(spec)
    h = best["h"]
    cw = spec["coef_width"]
    tried = []
    chosen = None
    for width in range(cw, 33):
        q, scale = quantise(h, width)
        met = response_metrics(q, spec["fs_in_hz"], spec["pass_edge_hz"], spec["stop_edge_hz"], comp_db(spec))
        ok = met["passband_ripple_db"] <= spec["ripple_db"] and met["stopband_atten_db"] >= spec["atten_db"]
        tried.append({"coef_width": width, "ok": bool(ok), **met})
        if chosen is None and ok:
            chosen = (width, q, scale, met)
            break
    if chosen is None:
        raise ValueError("quantised filter does not meet the spec up to 32 bits")
    width, q, scale, met = chosen
    return {
        "candidates": [{k: v for k, v in c.items() if k != "h"} for c in cands],
        "method": best["method"],
        "taps": best["taps"],
        "float_metrics": {"passband_ripple_db": best["passband_ripple_db"], "stopband_atten_db": best["stopband_atten_db"]},
        "requested_coef_width": cw,
        "coef_width": width,
        "quantised_metrics": met,
        "attenuation_lost_db": best["stopband_atten_db"] - met["stopband_atten_db"],
        "width_search": tried,
        "scale": float(scale),
        "dc_gain_int": int(np.sum(q)),
        "symmetric": bool(np.array_equal(q, q[::-1])),
        "h_float": h,
        "coef": q,
    }


def response_curve(h, fs, n=1024):
    """(frequency Hz, gain dB) of the DC-normalised response, for plot data."""
    h = np.asarray(h, dtype=float) / np.sum(h)
    w, H = signal.freqz(h, worN=n, fs=fs)
    return w, 20 * np.log10(np.abs(H) + 1e-12)


def coe_text(coef, radix=10):
    """The Xilinx `.coe` file for a coefficient vector (decimal radix: integers as designed)."""
    vals = ",\n".join(str(int(c)) for c in coef)
    return f"radix = {radix};\ncoefdata =\n{vals};\n"
