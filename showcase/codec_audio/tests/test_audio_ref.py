"""Self-tests of the reference model: the arithmetic the RTL and the datasheet rely on (brief 78)."""
from __future__ import annotations

import random

from showcase.codec_audio.model import audio_ref as A


def test_slew_is_linear_and_exact():
    cur, seq = A.UNITY, []
    while cur != 0x0800:
        cur = A.slew(cur, 0x0800)
        seq.append(cur)
    assert len(seq) == 0x800 // A.RAMP_STEP == 128
    assert all(a - b == A.RAMP_STEP for a, b in zip(seq, seq[1:-1]))
    assert A.slew(0x0800, 0x0800) == 0x0800 and A.slew(5, 8) == 8 and A.slew(8, 5) == 5


def test_gain_floor_and_saturation():
    assert A.apply_gain(-1, 0x0800) == -1          # floor, not truncation toward zero
    assert A.apply_gain(1, 0x0800) == 0
    assert A.apply_gain(A.S_MAX, 0x2000) == A.S_MAX and A.apply_gain(A.S_MIN, 0x2000) == A.S_MIN
    assert A.apply_gain(A.S_MIN, 0x1000) == A.S_MIN


def test_peak_hold_then_decay():
    m = A.Meters(hold=3)
    m.feed(1000)
    assert (m.peak, m.hold_left) == (1000, 3)
    for left in (2, 1, 0):
        m.feed(0)
        assert (m.peak, m.hold_left) == (1000, left)
    m.feed(0)
    assert m.peak == 1000 - (1000 >> A.DECAY_SHIFT)
    m.feed(-1000)
    assert m.peak == 1000 and m.hold_left == 3      # an equal magnitude re-arms the hold


def test_peak_of_most_negative_sample_is_a_full_magnitude():
    m = A.Meters()
    m.feed(A.S_MIN)
    assert m.peak == 1 << 23 and m.clips == 1


def test_clip_counter_counts_samples_and_saturates():
    m = A.Meters()
    for y in (A.S_MAX, A.S_MAX, A.S_MIN, 5, A.S_MAX):
        m.feed(y)
    assert m.clips == 4
    m.clips = 0xFFFF
    m.feed(A.S_MAX)
    assert m.clips == 0xFFFF


def test_rms_window_matches_floor_sqrt():
    m = A.Meters(rms_log2=3)
    for y in (3, -3, 3, -3, 4, -4, 4, -4):
        m.feed(y)
    assert m.windows == 1 and m.rms == 3             # mean square 12 (floor of 100 / 8), sqrt 3.46 -> 3
    rng = random.Random(1)
    m = A.Meters(rms_log2=4)
    ys = [rng.randrange(A.S_MIN, A.S_MAX + 1) for _ in range(16)]
    for y in ys:
        m.feed(y)
    assert m.rms ** 2 <= sum(y * y for y in ys) // 16 < (m.rms + 1) ** 2


def test_rms_of_full_scale_square_wave():
    m = A.Meters(rms_log2=2)
    for y in (A.S_MAX, A.S_MIN, A.S_MAX, A.S_MIN):
        m.feed(y)
    assert m.rms == (1 << 23) - 1                    # mean square just under 2**46: the floor square root is S_MAX


def test_path_has_one_frame_latency_and_mute_ramps():
    p = A.Path(rms_log2=2)
    outs = [p.frame(1000 + k, -1000 - k) for k in range(4)]
    assert outs[0] == (0, 0) and outs[1] == (1000, -1000) and outs[3] == (1002, -1002)
    p.ch[0].mute = 1
    ys = [p.ch[0].process(0x400000) for _ in range(3)]
    assert ys == [(0x400000 * (0x1000 - 16 * (i + 1))) >> 12 for i in range(3)]


def test_i2s_bits_roundtrip():
    rng = random.Random(2)
    for _ in range(50):
        v = rng.randrange(A.S_MIN, A.S_MAX + 1)
        b = A.slot_bits(v)
        assert len(b) == 32 and b[0] == 0 and A.bits_slot(b) == v
    assert A.slot_bits(A.S_MIN)[1] == 1 and A.slot_bits(1)[24] == 1
