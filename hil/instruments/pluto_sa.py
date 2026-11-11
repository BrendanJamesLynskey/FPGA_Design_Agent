"""Swept spectrum analyser and tracking generator from an ADALM-Pluto (brief 30, the owner's idea 2026-11-10).

The swept-analyser maths (:func:`stitch`) is pure numpy and tested on synthetic IQ. The radio access (:func:`capture_iq`
and :func:`tracking_sweep`) needs pyadi-iio and libiio, which are not installed on this PC; they import lazily and have
NOT been run (no Pluto was connected on 2026-11-11). RF rules (house rules): the transmitter is never enabled unless the
caller states an attenuator of at least 30 dB (or a dummy load) in the path; with `atten_db < 30` the transmit path is
muted at -89.75 dB and the function receives only. Levels are relative (dBFS of the ADC) until calibrated against a known
source. Default range 325 MHz - 3.8 GHz (the stock firmware's limit; the wider range is a firmware change, i.e. a flash
write, and needs the owner's yes).
"""
from __future__ import annotations

import numpy as np

MIN_ATTEN_DB_FOR_TX = 30.0
STOCK_RANGE_HZ = (325e6, 3.8e9)


def block_spectrum(iq: np.ndarray, fs: float, mask_dc_bins: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Power spectrum (dBFS per bin, fftshifted, Blackman-Harris) of one IQ block; the DC/LO spike's bins are replaced by
    the median of their neighbours so the stitched trace has no spike at every centre."""
    n = len(iq)
    k = np.arange(n) * 2 * np.pi / n
    w = 0.35875 - 0.48829 * np.cos(k) + 0.14128 * np.cos(2 * k) - 0.01168 * np.cos(3 * k)
    X = np.fft.fftshift(np.fft.fft(iq * w))
    p = np.abs(X) ** 2 / (np.sum(w) ** 2)                    # a full-scale complex tone reads 0 dBFS
    c = n // 2
    for b in range(-mask_dc_bins, mask_dc_bins + 1):
        nb = np.r_[p[c + mask_dc_bins + 1: c + mask_dc_bins + 6], p[c - mask_dc_bins - 5: c - mask_dc_bins - 1]]
        p[c + b] = np.median(nb)
    f = np.fft.fftshift(np.fft.fftfreq(n, 1 / fs))
    return f, 10 * np.log10(p + 1e-30)


def stitch(blocks: list[np.ndarray], centers_hz: list[float], fs: float, usable: float = 0.8) -> tuple[np.ndarray, np.ndarray]:
    """Join the blocks of a sweep into one trace: from each block keep the central `usable` fraction of the bandwidth (the
    anti-alias filter rolls off at the edges), and place it at its centre frequency. Returns (freq Hz, dBFS)."""
    fs_out, ps_out = [], []
    for iq, fc in zip(blocks, centers_hz):
        f, p = block_spectrum(iq, fs)
        keep = np.abs(f) <= usable * fs / 2
        fs_out.append(f[keep] + fc)
        ps_out.append(p[keep])
    f_all, p_all = np.concatenate(fs_out), np.concatenate(ps_out)
    order = np.argsort(f_all)
    return f_all[order], p_all[order]


def sweep_centres(f_start: float, f_stop: float, fs: float, usable: float = 0.8) -> list[float]:
    step = fs * usable
    n = int(np.ceil((f_stop - f_start) / step))
    return [f_start + step / 2 + i * step for i in range(max(n, 1))]


def peaks(f: np.ndarray, p: np.ndarray, n: int = 5, min_sep_hz: float = 50e3) -> list[tuple[float, float]]:
    """The n strongest local maxima at least min_sep_hz apart: (freq, dB)."""
    order, out = np.argsort(p)[::-1], []
    for i in order:
        if all(abs(f[i] - fo) >= min_sep_hz for fo, _ in out):
            out.append((float(f[i]), float(p[i])))
        if len(out) == n:
            break
    return out


def spur_free_dynamic_range(f: np.ndarray, p: np.ndarray, carrier_hz: float, guard_hz: float = 100e3) -> float:
    c = np.abs(f - carrier_hz) <= guard_hz
    return float(p[c].max() - p[~c].max())


def capture_iq(uri: str, centre_hz: float, fs: float = 2.5e6, n: int = 65536, gain_db: float = 30.0) -> np.ndarray:
    """One IQ block from the Pluto's receiver (pyadi-iio; not run here). Receive only."""
    import adi                                               # type: ignore[import-not-found]
    sdr = adi.Pluto(uri=uri)
    sdr.sample_rate = int(fs)
    sdr.rx_lo = int(centre_hz)
    sdr.gain_control_mode_chan0 = "manual"
    sdr.rx_hardwaregain_chan0 = gain_db
    sdr.rx_buffer_size = n
    sdr.rx_destroy_buffer()
    sdr.rx()                                                  # discard one buffer after a retune
    iq = np.asarray(sdr.rx(), dtype=complex) / 2048.0         # 12-bit ADC, full scale +-2048
    return iq


def tracking_sweep(uri: str, f_start: float, f_stop: float, atten_db: float, fs: float = 2.5e6, tx_db: float = -30.0) -> tuple[np.ndarray, np.ndarray]:
    """Scalar network analyser: the transmitter sends a tone one bandwidth-quarter above each receive centre, through the
    device under test and at least 30 dB of attenuation, into the receiver. Refuses to transmit without the attenuation."""
    if atten_db < MIN_ATTEN_DB_FOR_TX:
        raise PermissionError(f"tracking generator needs >= {MIN_ATTEN_DB_FOR_TX} dB attenuator or a dummy load; got {atten_db} dB. Receive only.")
    if not (STOCK_RANGE_HZ[0] <= f_start < f_stop <= STOCK_RANGE_HZ[1]):
        raise ValueError(f"sweep outside the stock range {STOCK_RANGE_HZ}")
    import adi                                               # type: ignore[import-not-found]
    sdr = adi.Pluto(uri=uri)
    sdr.sample_rate = int(fs)
    sdr.tx_hardwaregain_chan0 = tx_db
    t = np.arange(65536) / fs
    tone = (2 ** 14) * np.exp(2j * np.pi * (fs / 4) * t)
    f_out, p_out = [], []
    try:
        for fc in sweep_centres(f_start, f_stop, fs / 2):
            sdr.tx_lo = int(fc)
            sdr.rx_lo = int(fc)
            sdr.tx_cyclic_buffer = True
            sdr.tx(tone)
            sdr.rx_buffer_size = 65536
            sdr.rx()
            iq = np.asarray(sdr.rx(), dtype=complex) / 2048.0
            f, p = block_spectrum(iq, fs)
            k = int(np.argmax(p))
            f_out.append(fc + f[k])
            p_out.append(p[k])
    finally:
        sdr.tx_destroy_buffer()
        sdr.tx_hardwaregain_chan0 = -89.75                  # mute on any exit
    return np.array(f_out), np.array(p_out)
