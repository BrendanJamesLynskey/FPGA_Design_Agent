"""The MAC model (arith/mac/model.py) against a plain-integer formulation (arith brief 139a)."""
from __future__ import annotations

import random

from arith.mac import model
from arith.tools import arith_common as ac


def reference(wa, wb, lanes, accw, signed, lat, seq):
    """A second, structure-free model: apply the samples one by one with Python integers; a sample presented at edge t is visible from edge t + lat - 1
    unless a reset at an edge up to t + lat - 2 (or at t) removes it. Returns the accumulator visible after each edge."""
    out, acc = [], 0
    applied = [None] * len(seq)                    # edge at which each surviving sample is applied
    for t, (rst, en, clr, a, b) in enumerate(seq):
        if en and not rst:
            applied[t] = t + lat - 1
    for t, (rst, en, clr, a, b) in enumerate(seq):
        if rst:
            for s in range(len(seq)):
                if applied[s] is not None and s <= t and applied[s] > t:
                    applied[s] = None              # in flight at the reset: dropped (a sample presented on a reset edge was never enabled)
    byedge = {}
    for s, e in enumerate(applied):
        if e is not None:
            byedge[e] = s
    for t, (rst, en, clr, a, b) in enumerate(seq):
        if rst:
            acc = 0
        elif t in byedge:
            _, _, c, aa, bb = seq[byedge[t]]
            acc = ((0 if c else acc) + model.dot(wa, wb, lanes, signed, aa, bb)) % (1 << accw)
        out.append(acc)
    return out


def test_model_equals_the_structure_free_reference():
    rng = random.Random(1392)
    for _ in range(300):
        wa, wb, lanes = rng.choice([1, 2, 3, 5, 8]), rng.choice([1, 2, 3, 5, 8]), rng.choice([1, 2, 3])
        accw = wa + wb + rng.choice([0, 0, 1, 4])
        signed, lat = rng.getrandbits(1), rng.choice([1, 2, 3, 4])
        seq = [(int(rng.random() < 0.03), int(rng.random() < 0.8), int(rng.random() < 0.15), rng.getrandbits(lanes * wa), rng.getrandbits(lanes * wb)) for _ in range(60)]
        m = model.MacModel(wa, wb, lanes, accw, signed, lat)
        got = [m.step(*s) for s in seq]
        assert got == reference(wa, wb, lanes, accw, signed, lat, seq), (wa, wb, lanes, accw, signed, lat)


def test_a_clear_starts_a_new_sum_with_this_samples_product():
    m = model.MacModel(4, 4, 1, 12, 0, 1)
    assert [m.step(0, 1, 0, 3, 5), m.step(0, 1, 0, 2, 2), m.step(0, 1, 1, 7, 1), m.step(0, 0, 1, 9, 9), m.step(0, 1, 0, 1, 1)] == [15, 19, 7, 7, 8]


def test_signed_products_wrap_modulo_the_accumulator_width():
    m = model.MacModel(4, 4, 1, 8, 1, 1)
    assert m.step(0, 1, 1, 0x8, 0x7) == (-8 * 7) % 256         # -56 in 8 bits
    assert m.step(0, 1, 0, 0x8, 0x8) == (-56 + 64) % 256


def test_reset_discards_the_samples_in_flight():
    m = model.MacModel(4, 4, 1, 12, 0, 3)
    m.step(0, 1, 0, 2, 2)
    m.step(0, 1, 0, 3, 3)
    assert m.step(1, 0, 0, 0, 0) == 0
    assert [m.step(0, 0, 0, 0, 0) for _ in range(3)] == [0, 0, 0]


def test_latency_expressions_match_the_model_table():
    spec = ac.load_spec("mac")
    for v, vd in spec["variants"].items():
        for p in vd["exhaustive_points"] + vd["random_points"] + vd["ooc_points"]:
            q = ac.merged_params(spec, v, p)
            assert ac.latency_of(spec, v, q) == model.LATENCY[v](q), (v, q)
