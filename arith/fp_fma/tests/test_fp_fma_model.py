"""The multiply-add models (arith/fp_fma/model.py, which call arith/fp_common/fp_ref.py) against independent formulations (arith brief 139e).

fused: an enumeration of every finite value of a tiny format (the nearest one, ties to even) for every triple, identities with the multiplier and the adder, and the pinned
special cases. cascade: equal to the multiplier followed by the adder, and its error against the exact value measured against the bound that spec.md states."""
from __future__ import annotations

import itertools
import random
from fractions import Fraction

import pytest

from arith.fp_common import fp_ref
from arith.fp_fma import model
from arith.tools import arith_common as ac


def _expected(f, subnorm, tab, sg, q):
    ne = fp_ref.nearest_even(f, subnorm, q, tab)
    if ne is None:
        return f.inf(sg)
    if not subnorm and (ne >> f.man) <= 0:
        return f.zero(sg)
    return ne | (sg << (f.w - 1))


@pytest.mark.parametrize("exp,man", [(2, 1), (2, 2), (3, 1)])
@pytest.mark.parametrize("subnorm", [0, 1])
def test_fused_equals_enumeration_exhaustively(exp, man, subnorm):
    f = fp_ref.Fmt(exp, man)
    tab = fp_ref.finite_values(f, subnorm)
    fin = [(x, *fp_ref.classify(f, x, subnorm)) for x in range(1 << f.w)]
    fin = [(x, s, q) for x, k, s, q in fin if k == "fin"]
    for (a, sa, qa), (b, sb, qb), (c, sc, qc) in itertools.product(fin, repeat=3):
        p = qa * qb
        q = (-p if sa ^ sb else p) + (-qc if sc else qc)
        if q == 0:
            continue
        assert model.fma(exp, man, subnorm, a, b, c) == _expected(f, subnorm, tab, 1 if q < 0 else 0, abs(q)), (exp, man, subnorm, a, b, c)


@pytest.mark.parametrize("exp,man,subnorm", [(2, 2, 1), (3, 2, 1), (3, 2, 0), (5, 10, 1), (8, 23, 1), (8, 23, 0), (8, 7, 1)])
def test_fused_reduces_to_the_adder_and_the_multiplier(exp, man, subnorm):
    f = fp_ref.Fmt(exp, man)
    rng = random.Random(1393 + exp + man)
    edges = fp_ref.edge_patterns(f)
    one = f.bias << f.man
    for _ in range(6000):
        a, c = fp_ref.rand_pattern(rng, f, edges), fp_ref.rand_pattern(rng, f, edges)
        b = fp_ref.rand_pattern(rng, f, edges)
        assert model.fma(exp, man, subnorm, a, one, c) == fp_ref.fp_add(f, subnorm, a, c), (hex(a), hex(c))              # a * 1 + c is a + c
        assert model.fma(exp, man, subnorm, one, a, c) == fp_ref.fp_add(f, subnorm, a, c), (hex(a), hex(c))
        prod = fp_ref.fp_mul(f, subnorm, a, b)
        z = model.fma(exp, man, subnorm, a, b, 0)
        # a * b + (+0): the product itself, except a product of exactly -0 which a +0 addend turns into +0 (round to nearest)
        assert z == prod or (prod == f.zero(1) and z == f.zero(0)), (hex(a), hex(b), hex(z), hex(prod))


def test_conventions_that_a_user_could_guess_wrong():
    one, two, three = 0x3F800000, 0x40000000, 0x40400000
    qnan, inf = 0x7FC00000, 0x7F800000
    assert model.fma(8, 23, 1, two, three, one) == 0x40E00000                            # 2 * 3 + 1 = 7
    assert model.fma(8, 23, 1, inf, 0, one) == qnan                                      # infinity * 0 + c is NaN
    assert model.fma(8, 23, 1, inf, 0, qnan) == qnan
    assert model.fma(8, 23, 1, 0, inf, inf) == qnan
    assert model.fma(8, 23, 1, inf, one, inf | 0x80000000) == qnan                       # infinity + (-infinity)
    assert model.fma(8, 23, 1, inf, one, inf) == inf                                     # same sign is fine
    assert model.fma(8, 23, 1, one, one, inf | 0x80000000) == inf | 0x80000000
    assert model.fma(8, 23, 1, 0x80000000, one, 0x80000000) == 0x80000000                # (-0) * 1 + (-0) is -0
    assert model.fma(8, 23, 1, 0x80000000, one, 0x00000000) == 0x00000000                # (-0) + (+0) is +0
    assert model.fma(8, 23, 1, two, three, 0xC0C00000) == 0x00000000                     # 2 * 3 + (-6): an exact cancellation is +0
    assert model.fma(8, 23, 0, 0x00000001, one, 0x00000001) == 0x00000000                # flush to zero: subnormal addend is zero
    assert model.fma(8, 23, 1, 0x00000001, one, 0x00000001) == 0x00000002
    # one rounding instead of two: (1 + 2^-23) * (1 - 2^-24) - 1 = 2^-24 - 2^-47 exactly; the cascade rounds the product (1 + 2^-24 - 2^-47, just below a tie) to 1.0 first and gets 0
    a, b, c = 0x3F800001, 0x3F7FFFFF, 0xBF800000
    assert model.fma(8, 23, 1, a, b, c) == 0x337FFFFE                                    # 2^-24 - 2^-47, kept by the fused operation
    assert model.cascade(8, 23, 1, a, b, c) == 0x00000000                                # lost by the cascade
    assert fp_ref.fp_mul(fp_ref.Fmt(8, 23), 1, a, b) == 0x3F800000


def test_cascade_is_the_multiplier_then_the_adder():
    for exp, man, subnorm in [(2, 2, 1), (3, 2, 0), (5, 10, 1), (8, 23, 1)]:
        f = fp_ref.Fmt(exp, man)
        rng = random.Random(1394 + exp)
        edges = fp_ref.edge_patterns(f)
        for _ in range(4000):
            a, b, c = (fp_ref.rand_pattern(rng, f, edges) for _ in range(3))
            assert model.cascade(exp, man, subnorm, a, b, c) == fp_ref.fp_add(f, subnorm, fp_ref.fp_mul(f, subnorm, a, b), c)


def _value(f, x, subnorm=1):
    k, s, q = fp_ref.classify(f, x, subnorm)
    return k, (-q if s else q)


def _ulp(f, x):
    """The unit in the last place of the finite pattern x (the subnormal step for zeros and subnormals)."""
    e = (x >> f.man) & f.emax_field
    return Fraction(2) ** ((max(e, 1)) - f.bias - f.man)


def _errors(f, triples):
    """(exact value, cascade error in ulps of the rounded product plus of the result, error in ulps of the result, |y| >= |p|/2) for finite results."""
    out = []
    for a, b, c in triples:
        ka, va = _value(f, a)
        kb, vb = _value(f, b)
        kc, vc = _value(f, c)
        if "nan" in (ka, kb, kc) or "inf" in (ka, kb, kc):
            continue
        exact = va * vb + vc
        p = fp_ref.fp_mul(f, 1, a, b)
        y = model.cascade(f.exp, f.man, 1, a, b, c)
        kp, vp = _value(f, p)
        ky, vy = _value(f, y)
        if kp != "fin" or ky != "fin":
            continue
        err = abs(vy - exact)
        out.append((err, _ulp(f, p) / 2 + _ulp(f, y) / 2, err / _ulp(f, y), abs(vy) * 2 >= abs(vp), exact, vy))
    return out


def test_cascade_error_bound_of_spec_md():
    """|cascade - exact| <= 0.5 ulp(rounded product) + 0.5 ulp(result); at most 1.5 ulp of the result when |y| >= |product|/2; unbounded in ulps of the result under cancellation."""
    f = fp_ref.Fmt(3, 2)
    tri = [(a, b, c) for a, b, c in itertools.product(range(1 << f.w), repeat=3)]
    res = _errors(f, tri)
    assert res
    assert all(e <= bound for e, bound, _, _, _, _ in res)
    assert all(u <= Fraction(3, 2) for _, _, u, ok, _, _ in res if ok)
    worst_cancel = max(u for _, _, u, ok, _, _ in res if not ok)
    assert worst_cancel > 2                                       # under cancellation the cascade is more than two ulps of its own result away
    rng = random.Random(1395)
    f = fp_ref.Fmt(5, 10)
    edges = fp_ref.edge_patterns(f)
    tri = [tuple(fp_ref.rand_pattern(rng, f, edges) for _ in range(3)) for _ in range(20000)]
    res = _errors(f, tri)
    assert all(e <= bound for e, bound, _, _, _, _ in res)
    assert all(u <= Fraction(3, 2) for _, _, u, ok, _, _ in res if ok)


def test_latency_expressions_match_the_model_table():
    spec = ac.load_spec("fp_fma")
    for v, vd in spec["variants"].items():
        for p in vd["exhaustive_points"] + vd["random_points"] + vd["ooc_points"]:
            q = ac.merged_params(spec, v, p)
            assert ac.latency_of(spec, v, q) == model.LATENCY[v](q), (v, q)
