"""Brief 19: the signal-chain model (no Vivado): converter model, measurements, CIC golden, the picture."""
import math

import numpy as np
import pytest

pytest.importorskip("scipy")

from scipy import signal  # noqa: E402

from flow.ipgen import chain, chain_svg, cic_design  # noqa: E402


def test_tone_metrics_recover_a_known_snr():
    fs, n = 48000.0, 16384
    k = 347
    f0 = k * fs / n
    t = np.arange(n) / fs
    rng = np.random.default_rng(1)
    amp = 0.5
    sigma = math.sqrt((amp ** 2 / 2) / 10 ** (60 / 10) * (fs / 2) / 19980.0)  # 60 dB SNR in 20 Hz..20 kHz
    x = amp * np.sin(2 * np.pi * f0 * t) + sigma * rng.standard_normal(n)
    m = chain.tone_metrics(x, fs, [f0])
    assert abs(m["sinad_db"] - 60) < 1.0
    assert abs(m["tone_dbfs"] - 20 * math.log10(amp)) < 0.01
    assert abs(m["enob_bits"] - (m["sinad_db"] - 1.76 - m["tone_dbfs"]) / 6.02) < 1e-9


def test_tone_metrics_see_a_harmonic():
    fs, n = 48000.0, 16384
    f0 = 347 * fs / n
    t = np.arange(n) / fs
    x = np.sin(2 * np.pi * f0 * t) + 1e-3 * np.sin(2 * np.pi * 3 * f0 * t)
    m = chain.tone_metrics(x, fs, [f0])
    assert abs(m["thd_db"] - (-60)) < 1.0
    assert abs(m["sfdr_db"] - 60) < 1.5


def test_ntf_peak_gain_and_modulator_tracks_input():
    b, a = chain.ntf_butterworth(4, 1.5)
    _, h = signal.freqz(b, a, worN=4096)
    assert abs(np.max(np.abs(h)) - 1.5) < 1e-3
    assert b[0] == pytest.approx(1.0) and a[0] == pytest.approx(1.0)
    n = 40000
    u = 0.1 * np.sin(2 * np.pi * 0.001 * np.arange(n))
    y = chain.pdm_modulate(u, b, a)
    assert set(np.unique(y)) == {-1.0, 1.0}
    assert abs(np.mean(y[:2000]) - np.mean(u[:2000])) < 0.05


def test_cic_golden_matches_recursive_hogenauer():
    R, M, N = 5, 1, 3
    rng = np.random.default_rng(3)
    x = rng.choice([-1, 1], 400).astype(np.int64)
    ints = x.copy()
    for _ in range(N):
        ints = np.cumsum(ints)
    dec = ints[::R]
    for _ in range(N):
        dec = np.concatenate([[dec[0]], dec[1:] - dec[:-1]]) if M == 1 else dec
    # the comb section above uses zero state for the sample before the first one
    assert np.array_equal(dec, cic_design.golden(x, R, M, N)[::R])


def test_cic_design_picks_fewest_stages_and_bit_growth():
    d = cic_design.design(dict(fs_in_hz=2.4e6, decimation=25, passband_hz=20000, alias_atten_db=45, input_width=2))
    assert d["stages"] == 4 and d["full_precision_width"] == 21 and d["gain"] == 25 ** 4


def test_svg_renders_with_numbers():
    blocks = [{"title": "A", "sub": "x", "lines": ["one", "-", "two"], "external": True}, {"title": "B", "sub": "y", "lines": ["z"]}]
    links = [{"lines": ["l0", "l1", "l2", "l3"]}]
    strip = {"title": "t", "sub": "s", "rows": [{"label": "n", "measured": 60.0, "predicted": 61.0, "enob": 10.0}]}
    svg = chain_svg.render("T", blocks, links, strip, ("f0", "f1"))
    assert svg.startswith("<svg") and "60.0 dB" in svg and "predicted 61.0 dB" in svg
