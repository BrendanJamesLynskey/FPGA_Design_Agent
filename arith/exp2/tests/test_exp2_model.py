"""The exp2 models (arith/exp2/model.py) against independent formulations and the pinned conventions of spec.md (arith brief 139d)."""
from __future__ import annotations

import math
from fractions import Fraction

from arith.exp2 import model
from arith.tools import arith_common as ac
from arith.tools import fxlib


def round_half_up(fr: Fraction) -> int:
    return math.floor(fr + Fraction(1, 2))


def test_table_is_the_correctly_rounded_function_to_within_the_tables_own_rounding():
    for iw, ow in [(4, 4), (6, 8), (8, 8), (8, 12), (8, 16), (5, 16)]:
        for x in range(1 << iw):
            assert abs(model.compute("table", dict(IW=iw, OW=ow), x) - model.ideal(dict(IW=iw, OW=ow), x)) <= 0.5 + 2.0 ** -(20 - ow) + 1e-9, (iw, ow, x)


def test_lerp_equals_an_exact_rational_evaluation_of_its_formula():
    """The integer pipeline of the lerp variant (shifts and one rounding) is the exact value of c0 + s1 * d / 2**DB, rounded half up, using Fractions."""
    for iw, ow, sb in [(8, 8, 3), (9, 10, 4), (12, 12, 5), (10, 16, 6)]:
        c0, s1 = fxlib.rom_lerp("exp2", sb)
        db = iw - sb
        for x in range(1 << iw):
            i, d = x >> db, x & ((1 << db) - 1)
            exact = (Fraction(c0[i]) + Fraction(s1[i] * d, 1 << db)) / (1 << (fxlib.CF - ow))
            assert model.compute("lerp", dict(IW=iw, OW=ow, SB=sb), x) == min(max(round_half_up(exact), 0), (1 << ow) - 1)


def test_poly2_equals_horner_with_one_floor_and_one_rounding_in_fractions():
    for iw, ow, sb in [(8, 8, 3), (12, 12, 4), (10, 16, 5)]:
        a0, a1, a2 = fxlib.rom_poly("exp2", sb)
        db = iw - sb
        for x in range(0, 1 << iw, 3):
            i, d = x >> db, x & ((1 << db) - 1)
            p1 = math.floor(Fraction(a2[i] * d, 1 << db))
            exact = (Fraction(a0[i]) + Fraction((a1[i] + p1) * d, 1 << db)) / (1 << (fxlib.CF - ow))
            assert model.compute("poly2", dict(IW=iw, OW=ow, SB=sb), x) == min(max(round_half_up(exact), 0), (1 << ow) - 1)


def test_cordic_follows_a_floating_point_hyperbolic_cordic_to_a_few_last_places():
    """A float CORDIC with the same shift sequence (no rounding of the constants and the shifts) lands within the model's own rounding of it."""
    iw, ow, nit, g = 12, 12, 16, 5
    seq = fxlib.hyp_seq(nit)
    gain = math.prod(math.sqrt(1 - 4.0 ** -i) for i in seq)
    for x in range(0, 1 << iw, 37):
        z = x / (1 << iw) * math.log(2)
        xx, yy = 1 / gain, 0.0
        for i in seq:
            d = 1 if z >= 0 else -1
            xx, yy, z = xx + d * yy * 2.0 ** -i, yy + d * xx * 2.0 ** -i, z - d * math.atanh(2.0 ** -i)
        assert abs(model.compute("cordic", dict(IW=iw, OW=ow, NIT=nit, G=g), x) - (xx + yy - 1) * (1 << ow)) < 2.0


def test_conventions_the_spec_pins():
    for v, p in [("table", dict(IW=8, OW=12, REG=1)), ("lerp", dict(IW=12, OW=12, SB=5)), ("poly2", dict(IW=12, OW=12, SB=4))]:
        assert model.compute(v, p, 0) == 0                                     # 2**0 = 1: the fraction is 0
        top = model.compute(v, p, (1 << p["IW"]) - 1)
        assert abs(top - model.ideal(p, (1 << p["IW"]) - 1)) <= 1.5 and top < 1 << p["OW"]     # the largest input is just below the end of the range
    p = dict(IW=8, OW=12, REG=1)
    assert model.compute("table", p, 128) == round(1.4142135623730951 * (1 << 12)) - (1 << 12)     # x = 0.5 gives sqrt 2
    assert model.compute("cordic", dict(IW=12, OW=12, NIT=16, G=5), 0) <= 1


def test_table_and_lerp_are_monotone():
    for v, p in [("table", dict(IW=8, OW=12, REG=1)), ("lerp", dict(IW=12, OW=12, SB=5)), ("lerp", dict(IW=16, OW=16, SB=6))]:
        ys = [model.compute(v, p, x) for x in range(1 << p["IW"])]
        assert all(a <= b for a, b in zip(ys, ys[1:])), (v, p)


def test_the_variants_are_not_bit_identical():
    p = dict(IW=12, OW=12, SB=5, NIT=16, G=5, REG=1)
    outs = {v: [model.compute(v, {**p, "IW": 8} if v == "table" else p, x) for x in range(256)] for v in ("table", "lerp", "poly2", "cordic")}
    assert len({tuple(o) for o in outs.values()}) == 4


def test_latency_expressions_match_the_model_table():
    spec = ac.load_spec("exp2")
    for v, vd in spec["variants"].items():
        for p in vd["exhaustive_points"] + vd["random_points"] + vd["ooc_points"]:
            q = ac.merged_params(spec, v, p)
            assert ac.latency_of(spec, v, q) == model.LATENCY[v](q), (v, q)
