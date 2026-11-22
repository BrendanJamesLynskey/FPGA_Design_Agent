"""The floating-point adder model (arith/fp_add/model.py, which calls arith/fp_common/fp_ref.py) against independent formulations (arith brief 139e).

Independent means: an enumeration of every finite value of a tiny format with the nearest one chosen directly (ties to even), and NumPy's float32 and float16 multiplication (the host's
IEEE hardware). The special-case and flush-to-zero conventions, which no external library shares, are pinned by examples."""
from __future__ import annotations

import random
import struct

import numpy as np
import pytest

from arith.fp_mul import model
from arith.fp_common import fp_ref
from arith.tools import arith_common as ac


def _nearest_expected(f, subnorm, tab, sg, q):
    """The pattern the enumeration gives for the exact finite magnitude q with sign sg (q > 0), including the flush-to-zero reading."""
    ne = fp_ref.nearest_even(f, subnorm, q, tab)
    if ne is None:
        return f.inf(sg)
    if not subnorm and (ne >> f.man) <= 0:
        return f.zero(sg)
    return ne | (sg << (f.w - 1))


@pytest.mark.parametrize("exp,man", [(2, 1), (2, 2), (3, 2)])
@pytest.mark.parametrize("subnorm", [0, 1])
def test_model_equals_enumeration_exhaustively(exp, man, subnorm):
    f = fp_ref.Fmt(exp, man)
    tab = fp_ref.finite_values(f, subnorm)
    for a in range(1 << f.w):
        ka, sa, qa = fp_ref.classify(f, a, subnorm)
        if ka != "fin":
            continue
        for b in range(1 << f.w):
            kb, sb, qb = fp_ref.classify(f, b, subnorm)
            if kb != "fin":
                continue
            q = qa * qb
            if q == 0:
                assert model.mul(exp, man, subnorm, a, b) == f.zero(sa ^ sb)
                continue
            assert model.mul(exp, man, subnorm, a, b) == _nearest_expected(f, subnorm, tab, sa ^ sb, q), (exp, man, subnorm, a, b)


def _f32(x: int) -> np.float32:
    return np.frombuffer(struct.pack("<I", x), dtype=np.float32)[0]


def _f32_bits(v) -> int:
    return struct.unpack("<I", np.float32(v).tobytes())[0]


def test_model_equals_numpy_float32():
    f = fp_ref.Fmt(8, 23)
    rng = random.Random(1391)
    edges = fp_ref.edge_patterns(f)
    with np.errstate(all="ignore"):
        for i in range(30000):
            a = fp_ref.rand_pattern(rng, f, edges)
            b = fp_ref.partner_pattern(rng, f, a) if i % 3 == 0 else fp_ref.rand_pattern(rng, f, edges)
            want = _f32_bits(_f32(a) * _f32(b))
            if np.isnan(_f32(want)):
                want = f.qnan()                        # numpy's NaN pattern differs: the library's NaN is canonical
            assert model.mul(8, 23, 1, a, b) == want, (hex(a), hex(b))


def test_model_equals_numpy_float16():
    f = fp_ref.Fmt(5, 10)
    rng = random.Random(1392)
    edges = fp_ref.edge_patterns(f)
    with np.errstate(all="ignore"):
        for i in range(30000):
            a = fp_ref.rand_pattern(rng, f, edges)
            b = fp_ref.partner_pattern(rng, f, a) if i % 3 == 0 else fp_ref.rand_pattern(rng, f, edges)
            fa = np.frombuffer(struct.pack("<H", a), dtype=np.float16)[0]
            fb = np.frombuffer(struct.pack("<H", b), dtype=np.float16)[0]
            r = fa * fb
            want = struct.unpack("<H", np.float16(r).tobytes())[0]
            if np.isnan(r):
                want = f.qnan()
            assert model.mul(5, 10, 1, a, b) == want, (hex(a), hex(b))


def test_conventions_that_a_user_could_guess_wrong():
    one32 = 0x3F800000
    qnan32 = 0x7FC00000
    inf32 = 0x7F800000
    assert model.mul(8, 23, 1, 0x80000000, 0x80000000) == 0x00000000                     # (-0) * (-0) is +0
    assert model.mul(8, 23, 1, 0x80000000, one32) == 0x80000000                          # (-0) * 1 is -0
    assert model.mul(8, 23, 1, inf32, 0x00000000) == qnan32                              # infinity * 0 is NaN
    assert model.mul(8, 23, 1, 0x00000000, inf32 | 0x80000000) == qnan32
    assert model.mul(8, 23, 0, inf32, 0x00000001) == qnan32                              # flush to zero: infinity * a subnormal is infinity * 0
    assert model.mul(8, 23, 1, inf32, 0x00000001) == inf32                               # ... but a nonzero number with subnormals
    assert model.mul(8, 23, 1, inf32 | 0x80000000, 0x40000000) == inf32 | 0x80000000     # infinity * 2 keeps the xor sign
    assert model.mul(8, 23, 1, 0x7F800001, one32) == qnan32                              # signalling NaN: canonical quiet NaN, payload dropped
    assert model.mul(8, 23, 1, 0xFFC12345, one32) == qnan32                              # and sign dropped
    assert model.mul(8, 23, 1, 0x7F7FFFFF, 0x40000000) == inf32                          # overflow rounds to infinity
    assert model.mul(8, 23, 1, 0x00000001, 0x3F000000) == 0x00000000                     # half the smallest subnormal ties to even (0)
    assert model.mul(8, 23, 1, 0x00000003, 0x3F000000) == 0x00000002                     # 1.5 smallest subnormals ties to even (2)
    assert model.mul(8, 23, 1, 0x00800000, 0x3F000000) == 0x00400000                     # smallest normal / 2 is a subnormal
    assert model.mul(8, 23, 0, 0x00800000, 0x3F000000) == 0x00000000                     # ... and is flushed with SUBNORM = 0
    assert model.mul(8, 23, 0, 0x00FFFFFE, 0x3F000001) == 0x00800000                     # a product just below the smallest normal number that rounds up to it is NOT flushed
    assert model.mul(8, 23, 0, 0x00FFFFFE, 0x3F000000) == 0x00000000                     # (the same operand times exactly 0.5 is below it by a whole ulp: flushed)
    assert model.mul(8, 7, 1, 0x3FC0, 0x4000) == 0x4040                                  # bfloat16: 1.5 * 2 = 3


def test_latency_expressions_match_the_model_table():
    spec = ac.load_spec("fp_mul")
    for v, vd in spec["variants"].items():
        for p in vd["exhaustive_points"] + vd["random_points"] + vd["ooc_points"]:
            q = ac.merged_params(spec, v, p)
            assert ac.latency_of(spec, v, q) == model.LATENCY[v](q), (v, q)
