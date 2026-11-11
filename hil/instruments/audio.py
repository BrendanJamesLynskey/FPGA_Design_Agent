"""Audio capture and measurement (brief 30): record the Nexys audio out (or an I2S2 path) on the UMC22 or the onboard
line-in, then measure the tone. numpy only (the Blackman-Harris window is written out), so it runs in CI.

Levels are relative to the 16-bit full scale of the capture, at the owner's standard setting (UMC22 input 2, Hi-Z, gain
about 50 %), so they say "the tone arrived at about this level", not a calibrated voltage.
"""
from __future__ import annotations

import math
import subprocess
import wave
from pathlib import Path

import numpy as np


def record(path: Path, seconds: float = 4.0, device: str = "plughw:CODEC", fs: int = 48000, channels: int = 2) -> Path:
    """arecord to a WAV file (blocking; stops on its own after `seconds`)."""
    cmd = ["arecord", "-q", "-D", device, "-f", "S16_LE", "-r", str(fs), "-c", str(channels), "-d", str(int(math.ceil(seconds))), str(path)]
    subprocess.run(cmd, check=True, timeout=seconds + 15)
    return path


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        fs, ch = w.getframerate(), w.getnchannels()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, ch).astype(float) / 32768.0
    return a, fs


def _bh(n: int) -> np.ndarray:
    k = np.arange(n) * 2 * np.pi / n
    return 0.35875 - 0.48829 * np.cos(k) + 0.14128 * np.cos(2 * k) - 0.01168 * np.cos(3 * k)


def measure_tone(x: np.ndarray, fs: int, f_expect: float | None = None, band: tuple[float, float] = (50.0, 20000.0),
                 lobe: int = 6, n_harm: int = 9, skip_s: float = 0.5) -> dict[str, float]:
    """Frequency, level (dBFS rms), THD (harmonics 2..n_harm against the fundamental, %), SINAD and the noise floor of a
    mono record. The first `skip_s` seconds are dropped (start-up). Frequency is the peak bin refined by a parabola
    through the log magnitudes of the three bins around it."""
    x = np.asarray(x, dtype=float)[int(skip_s * fs):]
    x = x - x.mean()
    n = len(x)
    w = _bh(n)
    p = 2.0 * np.abs(np.fft.rfft(x * w)) ** 2 / (n * np.sum(w ** 2))        # a tone of amplitude A has A^2/2 in its lobe
    f = np.fft.rfftfreq(n, 1 / fs)
    df = f[1]
    inband = (f >= band[0]) & (f <= band[1])
    k0 = int(np.argmax(np.where(inband, p, 0.0)))
    if 1 <= k0 < len(p) - 1:
        a, b, c = np.log(p[k0 - 1] + 1e-30), np.log(p[k0] + 1e-30), np.log(p[k0 + 1] + 1e-30)
        k_ref = k0 + 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else k0
    else:
        k_ref = k0
    f0 = k_ref * df

    def lobe_bins(fc: float) -> np.ndarray:
        k = int(round(fc / df))
        return np.arange(max(k - lobe, 0), min(k + lobe + 1, len(p)))
    sig_b = lobe_bins(f0)
    sig = p[sig_b].sum()
    mask = inband.copy()
    mask[sig_b] = False
    harm_power = 0.0
    used = np.zeros(len(p), bool)
    for h in range(2, n_harm + 1):
        fh = h * f0
        if fh > min(band[1], fs / 2 - 10 * df):
            break
        b = lobe_bins(fh)
        b = b[mask[b] & ~used[b]]
        used[b] = True
        harm_power += p[b].sum()
    noise_dist = p[mask].sum()
    noise_only = max(noise_dist - harm_power, 1e-30)
    out = {"freq_hz": float(f0), "level_dbfs_rms": 10 * math.log10(max(sig, 1e-30)),
           "thd_percent": 100 * math.sqrt(harm_power / sig) if sig > 0 else float("nan"),
           "sinad_db": 10 * math.log10(sig / max(noise_dist, 1e-30)),
           "noise_floor_dbfs_per_bin": 10 * math.log10(float(np.median(p[mask])) + 1e-30)}
    if f_expect is not None:
        out["freq_error_hz"] = float(f0 - f_expect)
    return out


def tone_check(m: dict[str, float], f_expect: float, f_tol_hz: float = 2.0, min_level_dbfs: float = -70.0, max_thd_percent: float = 5.0,
               min_sinad_db: float = 15.0) -> dict:
    """Pass rule for a stimulus tone seen at the pins. Every threshold is in the result, so a failure names the one broken."""
    checks = {
        "freq": abs(m["freq_hz"] - f_expect) <= f_tol_hz,
        "level": m["level_dbfs_rms"] >= min_level_dbfs,
        "thd": m["thd_percent"] <= max_thd_percent,
        "sinad": m["sinad_db"] >= min_sinad_db,
    }
    return {"pass": all(checks.values()), "checks": checks, "measured": m,
            "limits": {"f_tol_hz": f_tol_hz, "min_level_dbfs": min_level_dbfs, "max_thd_percent": max_thd_percent, "min_sinad_db": min_sinad_db}}
