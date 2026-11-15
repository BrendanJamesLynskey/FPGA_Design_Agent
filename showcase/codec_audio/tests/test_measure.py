"""The PC-side measurement scripts against known signals and the simulated rig: no audio device, no board (brief 78)."""
from __future__ import annotations

import json
import random

import numpy as np
import pytest

from showcase.codec_audio.measure import audio_measure as M
from showcase.codec_audio.measure import run_measure
from showcase.codec_audio.model import audio_ref as A

FS = M.FS


def test_thd_n_of_a_known_third_harmonic():
    t = np.arange(FS) / FS
    x = 0.5 * np.sin(2 * np.pi * 1000 * t) + 0.005 * np.sin(2 * np.pi * 3000 * t)      # -40 dB
    r = M.thd_n(x, FS, 1000)
    assert r["thd_n_db"] == pytest.approx(-40.0, abs=0.3)
    assert r["thd_n_percent"] == pytest.approx(1.0, rel=0.05)
    assert r["fundamental_dbfs"] == pytest.approx(-6.02, abs=0.1)        # a 0.5 peak sine


def test_noise_floor_of_white_noise():
    x = 10 ** (-90 / 20) / np.sqrt(2) * np.random.default_rng(5).standard_normal(FS * 2)      # -90 dBFS rms (against a full-scale sine) over 24 kHz
    inband = M.noise_floor_dbfs(x, FS)
    assert inband == pytest.approx(-90 + 10 * np.log10(19980 / 24000), abs=0.6)


def test_crosstalk_of_a_known_leak():
    t = np.arange(FS) / FS
    a = 0.3 * np.sin(2 * np.pi * 1000 * t)
    assert M.crosstalk_db(a, 10 ** (-80 / 20) * a, FS, 1000) == pytest.approx(-80, abs=0.1)


def test_latency_to_a_fraction_of_a_sample():
    ref = M.noise_burst(1.0, -20)
    for lag in (0.0, 17.0, 123.5, 701.25):
        r = M.SimRig(codec_delay=lag, adc_noise_dbfs=-140, crosstalk_db=-140, h2_db=-140, h3_db=-140)
        y, _ = r.play_record(ref, np.zeros_like(ref))
        assert M.latency_samples(ref, y[:len(ref) + 800]) == pytest.approx(lag + 1.0, abs=0.15)     # +1: the path's own frame


def test_sim_rig_gain_stage_is_bit_exact_with_the_reference_model():
    rng = random.Random(4)
    n = 3000
    x = np.array([rng.randrange(-(1 << 23), 1 << 23) for _ in range(n)], dtype=np.int64)
    rig = M.SimRig(ramp_step=16)
    ev = [M.Event(500 / FS, "gain", 0, 0x2800), M.Event(1500 / FS, "mute", 0, 1), M.Event(2200 / FS, "mute", 0, 0)]
    got = rig._channel(x, 0, ev)
    ch, want = A.Channel(rms_log2=8), []
    for i in range(n):
        for e in ev:
            if round(e.t * FS) == i:
                if e.op == "gain":
                    ch.target = e.value
                else:
                    ch.mute = e.value
        want.append(ch.process(int(x[i])))
    assert got.tolist() == want


def test_step_is_found_and_the_ramp_clicks_less_than_a_step():
    x = M.tone(1000, 1.1, -20, FS, fade_ms=20)
    ev = [M.Event(0.6, "gain", 0, 0x0800)]
    out = {}
    for smooth in (True, False):
        r = M.SimRig(smooth=smooth, adc_noise_dbfs=-140, crosstalk_db=-140, h2_db=-140, h3_db=-140)
        y, _ = r.play_record(x, x, ev)
        out[smooth] = y
    at = M.step_index(out[False], FS)
    assert abs(at - int(0.6 * FS)) < 0.003 * FS
    cmp = M.compare_click(out[True], out[False], FS, 1000)
    assert cmp["improvement_db"] > 12.0 and cmp["smoothed_db"] < cmp["control_db"]


def test_classify_names_the_limiting_item():
    assert M.classify(-92, -90, -100)["limited_by"] == "pc_interface"
    assert M.classify(-97, -120, -100)["limited_by"] == "codec"
    assert M.classify(-60, -90, -100)["limited_by"] == "design_or_unknown"
    assert M.classify(-60, None, None)["limited_by"] == "design_or_unknown"


def test_wav_round_trip_is_exact_at_24_bits(tmp_path):
    x = np.array([0, 1 / 8388608.0, -1.0, 0.5, -0.5, 8388607 / 8388608.0, -1 / 8388608.0])
    M.write_wav(tmp_path / "a.wav", [x, x[::-1]])
    (l, r), fs = M.read_wav(tmp_path / "a.wav")
    assert fs == FS and np.array_equal(l, x) and np.array_equal(r, x[::-1])


def test_the_dry_run_writes_a_record_marked_as_a_dry_run(tmp_path):
    out = tmp_path / "r.json"
    assert run_measure.main(["--dry-run", "--quick", "--out", str(out)]) == 0
    r = json.loads(out.read_text())
    assert r["dry_run"] is True and r["rig"] == "sim" and r["host"] == "dry run"
    assert set(r) >= {"latency_samples", "frequency_response_db", "thd_n", "noise_floor_dbfs", "crosstalk_db", "click", "limits", "conditions"}
    assert r["click"]["improvement_db"] > 12 and r["latency_samples"] == pytest.approx(42.0, abs=0.2)
    assert r["limits"]["thd_n"]["limited_by"] == "design_or_unknown"       # no baseline and no datasheet given


def test_baseline_makes_the_interface_the_limit(tmp_path):
    base = tmp_path / "base.json"
    run_measure.main(["--dry-run", "--quick", "--out", str(base)])
    out = tmp_path / "r.json"
    run_measure.main(["--dry-run", "--quick", "--baseline", str(base), "--out", str(out)])
    r = json.loads(out.read_text())
    assert all(v["limited_by"] == "pc_interface" for v in r["limits"].values())


def test_a_real_run_refuses_without_devices_and_without_the_warning():
    with pytest.raises(SystemExit):
        run_measure.main(["--play-device", "plughw:X", "--record-device", "plughw:X"])        # no --confirm-owner-warned
    with pytest.raises(SystemExit):
        run_measure.main(["--confirm-owner-warned"])                                          # no devices


def test_levels_are_quoted_against_a_full_scale_sine():
    x = M.tone(1000, 1.0, 0.0, fade_ms=0)
    assert M.level_dbfs(x, FS, 1000) == pytest.approx(0.0, abs=0.05)
    assert M.level_dbfs(M.tone(1000, 1.0, -30, fade_ms=0), FS, 1000) == pytest.approx(-30.0, abs=0.05)


def test_a_tone_starts_and_ends_silent():
    x = M.tone(1000, 0.5, -30)
    assert abs(x[0]) < 1e-9 and abs(x[-1]) < 1e-3 and np.max(np.abs(x)) == pytest.approx(M.dbfs_to_amp(-30), rel=1e-3)
