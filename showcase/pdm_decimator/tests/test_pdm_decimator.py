"""Tests of the PDM audio-path model, its specification and the measurement scripts (brief 79, phase 1). No hardware, no simulator."""
from __future__ import annotations

import json
import math
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

from agent.graph.spec_schema import validate
from showcase.pdm_decimator.measure import pdm_measure as pm
from showcase.pdm_decimator.model import pdm_chain_ref as ref

HERE = Path(__file__).resolve().parents[1]
SPEC = yaml.safe_load((HERE / "spec.yaml").read_text())


def independent(bits) -> list[int]:
    """The same chain written as whole-array steps (cumulative sums, slicing), to check the streaming model against."""
    s = np.where(np.array(bits) > 0, 1, -1).astype(np.int64)
    v = np.cumsum(np.cumsum(np.cumsum(s)))[15::16]
    for _ in range(3):
        v = np.diff(v, prepend=0)
    x = [max(-32768, min(32767, int(c) * 8)) for c in v[2:]]

    def hb(xs):
        out = []
        for n in range(1, len(xs) + 1):
            if n % 2:
                continue
            taps = [xs[n - 1 - k] if n - 1 - k >= 0 else 0 for k in range(7)]
            acc = sum(c * t for c, t in zip((-1, 0, 9, 16, 9, 0, -1), taps))
            q, r = divmod(acc, 32)
            q += 1 if r > 16 or (r == 16 and q % 2 == 1) else 0
            out.append(max(-32768, min(32767, q)))
        return out

    x = hb(hb(x))
    f = []
    for n in range(len(x)):
        taps = [x[n - k] if n - k >= 0 else 0 for k in range(9)]
        f.append(max(-32768, min(32767, (sum(c * t for c, t in zip((2, -6, 16, -48, 584, -48, 16, -6, 2), taps)) + 256) >> 9)))
    out, xp, yp = [], 0, 0
    for v_ in f:
        y = max(-32768, min(32767, v_ - xp + yp - (yp >> 7)))
        out.append(y)
        xp, yp = v_, y
    return out


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_streaming_model_equals_the_whole_array_version(seed):
    rng = random.Random(seed)
    bits = [rng.randrange(2) for _ in range(9000)]
    assert ref.process(bits)[0] == independent(bits)


def test_full_scale_saturates_and_quiet_does_not():
    for b in (1, 0):
        out, sat = ref.process([b] * 3000)
        assert sat and out
    quiet = pm.delta_sigma(lambda k: 0.1 * math.sin(2 * math.pi * 2000 * k / ref.FS_PDM), ref.bits_needed(64) + 600)
    out, sat = ref.process(quiet)
    assert not sat and max(abs(v) for v in out) < 6000


def test_first_audio_sample_appears_at_the_stated_latency():
    bits = [1, 0] * 4000
    chain = ref.AudioChain()
    first = next(n for n, b in enumerate(bits, 1) if chain.push(b))
    assert first == ref.FIRST_SAMPLE_AT
    second = next(n for n, b in enumerate(bits[first:], first + 1) if chain.push(b))
    assert second - first == 64


def test_stage_facts():
    # CIC steady state is the exact +-4096 before scaling: 4096 * 8 = 32768 limits to 32767 and sets the flag
    chain = ref.AudioChain()
    for _ in range(16 * 8):
        chain.push(1)
    assert chain.saturated
    # half-band ties go to the even neighbour: ACC = 16, 48, -16, -48
    hb = ref._Halfband()
    got = []
    for x in (1, 3, -1, -3):                                    # the centre tap is 16, so ACC = 16 x
        hb.taps, hb.parity = [0] * 7, 1                         # the next push completes a pair
        hb.taps[2] = x                                          # the push shifts it to index 3, the centre tap
        got.append(hb.push(0))
    assert got == [0, 2, 0, -2]
    # DC blocker: floor shift leaves a positive output below 128 in place
    chain = ref.AudioChain()
    chain.x_prev, chain.y_prev = 100, 100
    assert chain.y_prev - (chain.y_prev >> ref.DC_SHIFT) == 100


def test_the_numbers_of_the_specification_hold_on_the_model():
    from showcase.pdm_decimator.model import product_numbers
    res = product_numbers.numbers()
    assert res["passband_worst_abs_db"] <= 1.0
    assert res["alias_worst_db"] <= -35.0
    assert res["snr_db_1khz_minus6dbfs_100hz_15khz"] >= 70.0
    assert res["full_scale_ones"]["saturates"] and res["full_scale_zeros"]["saturates"]
    pinned = json.loads((HERE / "records" / "model_numbers_2026-11-14.json").read_text())
    assert pinned["passband_worst_abs_db"] == res["passband_worst_abs_db"]
    assert pinned["snr_db_1khz_minus6dbfs_100hz_15khz"] == res["snr_db_1khz_minus6dbfs_100hz_15khz"]


def test_spec_is_valid_and_agrees_with_the_measurement_registers():
    assert validate(SPEC) == [], validate(SPEC)
    regs = {r["name"]: r["offset"] for r in SPEC["registers"]["map"]}
    assert (regs["CTRL"], regs["STATUS"], regs["COUNT"], regs["CAP"]) == (pm.CTRL, pm.STATUS, pm.COUNT, pm.CAP0)
    assert SPEC["parameters"]["CLK_HALF"] == 16 and ref.FS_PDM == 100e6 / (2 * SPEC["parameters"]["CLK_HALF"])
    assert abs(ref.FS_OUT - 48828.125) < 1e-9
    ids = [r["id"] for r in SPEC["requirements"]]
    assert ids == sorted(ids) and len(ids) == len(set(ids))


def test_tone_amplitude_and_noise_estimators_recover_known_signals():
    rng = np.random.default_rng(3)
    for f in pm.TONES_HZ:
        for _ in range(5):
            ph = rng.uniform(0, 2 * np.pi)
            rec = 0.3 * np.sin(2 * np.pi * f / pm.FS_OUT * np.arange(64) + ph) + 0.02
            assert abs(pm.tone_amplitude(rec, f) - 0.3) < 0.01
    white = [rng.normal(0, 10 ** (-80 / 20), 64) + 0.05 for _ in range(400)]
    assert abs(pm.noise_dbfs(white) - (-80)) < 0.5


def test_simulated_board_follows_the_capture_rules():
    tone = [None]
    board = pm.SimBoard(pm.simulated_room(np.random.default_rng(1), tone))
    assert board.read(pm.CAP0) == 0 and board.read(pm.STATUS) == 0
    board.write(pm.CTRL, pm.RUN)                              # RUN without ARM: nothing is captured
    assert board.read(pm.STATUS) & pm.DONE == 0
    board.write(pm.CTRL, pm.ARM | pm.RUN)                     # ARM while RUN is already 1 is ignored
    assert board.read(pm.STATUS) & pm.DONE == 0
    board.write(pm.CTRL, 0)
    rec = pm.capture(board)
    assert rec.shape == (64,) and board.read(pm.STATUS) & pm.DONE
    board.write(pm.CTRL, pm.ARM)                              # a new ARM clears DONE and CAP reads 0
    assert board.read(pm.STATUS) & pm.DONE == 0 and board.read(pm.CAP0) == 0


def test_dry_run_passes_and_records_that_it_is_one():
    res = pm.dry_run(records=8)
    assert res["dry_run"] and res["dry_run_pass"]
    assert [p["f_hz"] for p in res["points"]] == list(pm.TONES_HZ)
    assert all(abs(p["rel_db"]) <= pm.RESPONSE_LIMIT_DB for p in res["points"])
    assert "not a measurement of hardware" in res["rig_settings"]["note"]


def test_runner_dry_run_and_real_run_refusal(tmp_path):
    run = [sys.executable, str(HERE / "measure" / "run_measure.py")]
    ok = subprocess.run(run + ["--dry-run", "--out", str(tmp_path / "r.json")], cwd=HERE.parents[1], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    assert json.loads((tmp_path / "r.json").read_text())["dry_run"] is True
    bad = subprocess.run(run + ["--port", "/dev/null", "--out", str(tmp_path / "x.json")], cwd=HERE.parents[1], capture_output=True, text=True)
    assert bad.returncode != 0 and "confirm-owner-warned" in bad.stderr
    assert not (tmp_path / "x.json").exists()
