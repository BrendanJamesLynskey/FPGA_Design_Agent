"""The sincos models (arith/sincos/model.py) against independent formulations and the pinned conventions of spec.md (arith brief 139d)."""
from __future__ import annotations

import math
from fractions import Fraction

from arith.sincos import model
from arith.tools import arith_common as ac
from arith.tools import fxlib

POINTS = [("lerp", dict(PH=10, OW=10, SB=5)), ("poly2", dict(PH=10, OW=10, SB=4)), ("cordic", dict(PH=10, OW=10, NIT=10, G=3))]


def rhu(fr: Fraction) -> int:
    return math.floor(fr + Fraction(1, 2))


def test_lerp_first_quadrant_equals_an_exact_rational_evaluation():
    for ph, ow, sb in [(8, 8, 3), (10, 10, 5), (12, 12, 6)]:
        k, db, fb = ph - 2, ph - 2 - sb, ow - 1
        s0, s1 = fxlib.rom_lerp("sinq", sb)
        c0, c1 = fxlib.rom_lerp("cosq", sb)
        for o in range(1 << k):
            i, d = o >> db, o & ((1 << db) - 1)
            want = lambda a, b: min(max(rhu((Fraction(a[i]) + Fraction(b[i] * d, 1 << db)) / (1 << (fxlib.CF - fb))), 0), (1 << fb) - 1)
            assert model.quarter("lerp", dict(PH=ph, OW=ow, SB=sb), o) == (want(s0, s1), want(c0, c1)), (ph, ow, sb, o)


def test_cordic_follows_a_floating_point_cordic_to_a_few_last_places():
    ph, ow, nit, g = 12, 12, 12, 4
    gain = math.prod(math.sqrt(1 + 4.0 ** -i) for i in range(nit))
    for o in range(0, 1 << (ph - 2), 17):
        z = 2 * math.pi * o / (1 << ph)
        x, y = 1 / gain, 0.0
        for i in range(nit):
            d = 1 if z >= 0 else -1
            x, y, z = x - d * y * 2.0 ** -i, y + d * x * 2.0 ** -i, z - d * math.atan(2.0 ** -i)
        s, c = model.quarter("cordic", dict(PH=ph, OW=ow, NIT=nit, G=g), o)
        assert abs(s - y * (1 << (ow - 1))) < 3.5 and abs(c - x * (1 << (ow - 1))) < 3.5          # two CORDICs differ by up to the sum of their (about 1.7 place) errors


def test_quadrant_map_and_symmetries_hold_for_every_variant():
    for v, p in POINTS:
        k = p["PH"] - 2
        n = 1 << k
        for o in range(0, n, 5):
            s0, c0 = model.compute(v, p, o)
            assert model.compute(v, p, n + o) == (c0, -s0)
            assert model.compute(v, p, 2 * n + o) == (-s0, -c0)
            assert model.compute(v, p, 3 * n + o) == (-c0, s0)


def test_conventions_the_spec_pins():
    for v, p in POINTS[:2]:
        mx = (1 << (p["OW"] - 1)) - 1
        assert model.compute(v, p, 0) == (0, mx)                                    # +1.0 is full scale minus one place
        assert model.compute(v, p, 1 << (p["PH"] - 2)) == (mx, 0)                   # 90 degrees
        assert model.compute(v, p, 1 << (p["PH"] - 1)) == (0, -mx)                  # 180 degrees
        assert model.compute(v, p, 3 << (p["PH"] - 2)) == (-mx, 0)                  # 270 degrees
    for v, p in POINTS:
        for ph in range(1 << p["PH"]):
            s, c = model.compute(v, p, ph)
            assert -(1 << (p["OW"] - 1)) < s < (1 << (p["OW"] - 1)) and -(1 << (p["OW"] - 1)) < c < (1 << (p["OW"] - 1))      # -2**(OW-1) never occurs
    assert model.pattern(-1, 10) == 1023


def test_the_variants_are_not_bit_identical():
    outs = {v: [model.compute(v, p, ph) for ph in range(1 << 10)] for v, p in POINTS}
    assert len({tuple(o) for o in outs.values()}) == 3


def test_latency_expressions_match_the_model_table():
    spec = ac.load_spec("sincos")
    for v, vd in spec["variants"].items():
        for p in vd["exhaustive_points"] + vd["random_points"] + vd["ooc_points"]:
            q = ac.merged_params(spec, v, p)
            assert ac.latency_of(spec, v, q) == model.LATENCY[v](q), (v, q)
