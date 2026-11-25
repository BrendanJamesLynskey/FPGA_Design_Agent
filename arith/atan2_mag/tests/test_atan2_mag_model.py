"""The atan2_mag model (arith/atan2_mag/model.py) against independent formulations and the pinned conventions of spec.md (arith brief 139d)."""
from __future__ import annotations

import math
import random

from arith.atan2_mag import model
from arith.tools import arith_common as ac
from arith.tools import fxlib

P = dict(W=8, PH=12, NIT=14, G=12)


def test_axes_and_quadrants_are_pinned():
    q = 1 << (P["PH"] - 2)
    m = (1 << P["W"]) - 1
    for v in (1, 5, 100):
        for variant in ("cordic",):
            assert abs(model.compute(variant, P, v, 0)[0]) <= 1                                         # positive x axis: angle 0 (to a last place)
            assert abs(model.compute(variant, P, 0, v)[0] - q) <= 1                                     # +y: a quarter turn
            assert abs(model.compute(variant, P, -v & m, 0)[0] - 2 * q) <= 1                            # -x: half a turn
            assert abs(model.compute(variant, P, 0, -v & m)[0] - 3 * q) <= 1                            # -y: three quarters
    assert model.compute("cordic", P, 3, 4)[1] == 5 and model.compute("cordic", P, 6, 8)[1] == 10      # the 3-4-5 triangle
    assert model.compute("cordic", P, 0, 0)[1] == 0                                                    # the origin has magnitude 0


def test_model_follows_the_exact_functions_for_every_vector_at_small_width():
    p = dict(W=6, PH=10, NIT=12, G=8)
    ea, em = 0.0, 0.0
    for x in range(1 << p["W"]):
        for y in range(1 << p["W"]):
            if fxlib.to_signed(x, p["W"]) == 0 and fxlib.to_signed(y, p["W"]) == 0:
                continue
            a, m = model.compute("cordic", p, x, y)
            ia, im = model.ideal(p, x, y)
            ea, em = max(ea, model.angle_error(p, a, ia)), max(em, abs(m - im))
    assert ea < 0.7 and em < 0.6


def test_a_float_cordic_gives_the_same_angle_to_a_few_last_places():
    p = dict(W=10, PH=12, NIT=14, G=12)
    rng = random.Random(1393)
    gain = math.prod(math.sqrt(1 + 4.0 ** -i) for i in range(p["NIT"]))
    for _ in range(500):
        x, y = rng.getrandbits(10), rng.getrandbits(10)
        xs, ys = fxlib.to_signed(x, 10), fxlib.to_signed(y, 10)
        off = 0.0
        if xs < 0:
            xs, ys, off = -xs, -ys, 0.5
        z = 0.0
        for i in range(p["NIT"]):
            s = 1 if ys >= 0 else -1
            xs, ys, z = xs + s * ys * 2.0 ** -i, ys - s * xs * 2.0 ** -i, z + s * math.atan(2.0 ** -i) / (2 * math.pi)
        ang, mag = model.compute("cordic", p, x, y)
        assert model.angle_error(p, ang, ((z + off) % 1.0) * (1 << p["PH"])) < 1.5
        assert abs(mag - xs / gain) < 1.0


def test_reflection_adds_half_a_turn():
    rng = random.Random(1394)
    m = (1 << P["W"]) - 1
    for _ in range(300):
        x, y = rng.randrange(-100, 100), rng.randrange(-100, 100)
        if (x, y) == (0, 0):
            continue
        a, _ = model.compute("cordic", P, x & m, y & m)
        b, _ = model.compute("cordic", P, -x & m, -y & m)
        assert model.angle_error(P, (a + (1 << (P["PH"] - 1))) % (1 << P["PH"]), b) <= 2


def test_the_most_negative_input_does_not_overflow():
    p = dict(W=8, PH=12, NIT=14, G=12)
    a, m = model.compute("cordic", p, 128, 128)                                   # (-128, -128): the longest vector, 181.02
    assert m == 181 and model.angle_error(p, a, 5 * (1 << 12) / 8) <= 1          # 225 degrees


def test_both_variants_are_the_same_function():
    spec = ac.load_spec("atan2_mag")
    assert set(spec["variants"]) == {"cordic", "cordic_g2"}
    for x, y in [(3, 4), (200, 17), (5, 250)]:
        assert model.compute("cordic", P, x, y) == model.compute("cordic_g2", {**P, "GRP": 3}, x, y)


def test_latency_expressions_match_the_model_table():
    spec = ac.load_spec("atan2_mag")
    for v, vd in spec["variants"].items():
        for p in vd["exhaustive_points"] + vd["random_points"] + vd["ooc_points"]:
            q = ac.merged_params(spec, v, p)
            assert ac.latency_of(spec, v, q) == model.LATENCY[v](q), (v, q)
