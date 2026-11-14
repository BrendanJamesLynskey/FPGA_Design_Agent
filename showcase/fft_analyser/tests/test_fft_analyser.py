"""Tests of the FFT power-spectrum model and its specification (brief 79, phase 1). No simulator."""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import numpy as np
import pytest
import yaml

from agent.graph.spec_schema import validate
from showcase.fft_analyser.model import fft_ref as ref, product_numbers

HERE = Path(__file__).resolve().parents[1]
SPEC = yaml.safe_load((HERE / "spec.yaml").read_text())


def memory(n: int, seed: int) -> list[int]:
    rng = random.Random(seed)
    return [rng.randrange(-30000, 30000) for _ in range(n)]


@pytest.mark.parametrize("n,win,lg", [(64, 1, 0), (64, 2, 2), (64, 0, 3), (256, 1, 1), (256, 2, 0), (1024, 1, 0)])
def test_streaming_pipeline_equals_the_batch_definition(n, win, lg):
    m = memory(n, n + win + lg)
    assert ref.streamed_spectrum(m, win, lg) == ref.spectrum(m, win, lg)


def test_delay_feedback_latency_is_n_minus_one():
    n = 64
    pipe = ref.SdfPipeline(n)
    outs = [pipe.push(1000 if i == 0 else 0) for i in range(2 * n)]
    # an impulse at sample 0 gives a flat spectrum, the first bin of which leaves the pipeline n - 1 samples later
    assert pipe.latency() == n - 1
    assert outs[n - 1] == (outs[n - 1][0], 0) and outs[n - 1][0] != 0


def test_known_answers():
    n = 64
    assert ref.window_table(1, n)[:5] == [0, 79, 315, 705, 1247]
    assert ref.window_table(1, n)[16] == 16384 and ref.window_table(1, n)[32] == 32767
    assert ref.window_table(2, n)[:4] == [2621, 2694, 2911, 3270]
    assert ref.twiddle(1, 16) == (30273, -12539) and ref.twiddle(4, 16) == (0, -32767)
    # DC input of 20000 appears in bin 0 at the 1/N scaling: 20000 (the sum path rounds exactly for a constant)
    bins = ref.fft_frame([20000] * n)
    assert bins[0] == (20000, 0) and all(c == (0, 0) for c in bins[1:])
    # butterfly ties round up for both outputs
    assert ref.butterfly((1, 0), (2, 0), (16384, 0))[0] == (2, 0)
    assert ref.butterfly((-1, 0), (-2, 0), (16384, 0))[0] == (-1, 0)


def test_no_limit_can_act_on_sixteen_bit_inputs():
    rng = random.Random(9)
    for _ in range(40):
        x = [rng.choice((-32768, 32767)) for _ in range(64)]
        for c in ref.fft_frame(x):
            assert all(-32768 <= v <= 32767 for v in c)


def test_the_numbers_of_the_specification_hold_on_the_model():
    res = product_numbers.numbers()
    for a in res["accuracy_vs_float"]:
        assert a["worst_component_error_lsb"] <= 2.0, a
        assert a["rms_error_lsb"] < 0.5, a
    assert all(v >= 70.0 for v in res["sfdr_db_hann_8_frames_with_2lsb_dither"].values()), res["sfdr_db_hann_8_frames_with_2lsb_dither"]
    pinned = json.loads((HERE / "records" / "model_numbers_2026-11-14.json").read_text())
    assert pinned == res


def test_spec_is_valid_and_consistent():
    assert validate(SPEC) == [], validate(SPEC)
    ids = [r["id"] for r in SPEC["requirements"]]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    offsets = [r["offset"] for r in SPEC["registers"]["map"]]
    assert len(set(offsets)) == len(offsets)
    assert SPEC["parameters"]["N_MAX"] == 1024
