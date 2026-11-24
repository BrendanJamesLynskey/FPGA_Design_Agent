"""The floating-point adder model (arith/fp_add/model.py, which calls arith/fp_common/fp_ref.py) against independent formulations (arith brief 139e).

Independent means: an enumeration of every finite value of a tiny format with the nearest one chosen directly (ties to even), and NumPy's float32 and float16 addition (the host's
IEEE hardware). The special-case and flush-to-zero conventions, which no external library shares, are pinned by examples."""
from __future__ import annotations

import random
import struct

import numpy as np
import pytest

from arith.fp_add import model
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
            q = (-qa if sa else qa) + (-qb if sb else qb)
            if q == 0:
                continue
            assert model.add(exp, man, subnorm, a, b) == _nearest_expected(f, subnorm, tab, 1 if q < 0 else 0, abs(q)), (exp, man, subnorm, a, b)


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
            b = fp_ref.near_pattern(rng, f, a) if i % 3 == 0 else fp_ref.rand_pattern(rng, f, edges)
            want = _f32_bits(_f32(a) + _f32(b))
            if np.isnan(_f32(want)):
                want = f.qnan()                        # numpy's NaN pattern differs: the library's NaN is canonical
            assert model.add(8, 23, 1, a, b) == want, (hex(a), hex(b))


def test_model_equals_numpy_float16():
    f = fp_ref.Fmt(5, 10)
    rng = random.Random(1392)
    edges = fp_ref.edge_patterns(f)
    with np.errstate(all="ignore"):
        for i in range(30000):
            a = fp_ref.rand_pattern(rng, f, edges)
            b = fp_ref.near_pattern(rng, f, a) if i % 3 == 0 else fp_ref.rand_pattern(rng, f, edges)
            fa = np.frombuffer(struct.pack("<H", a), dtype=np.float16)[0]
            fb = np.frombuffer(struct.pack("<H", b), dtype=np.float16)[0]
            r = fa + fb
            want = struct.unpack("<H", np.float16(r).tobytes())[0]
            if np.isnan(r):
                want = f.qnan()
            assert model.add(5, 10, 1, a, b) == want, (hex(a), hex(b))


def test_conventions_that_a_user_could_guess_wrong():
    one32 = 0x3F800000
    qnan32 = 0x7FC00000
    assert model.add(8, 23, 1, one32, one32 | 0x80000000) == 0x00000000                  # x + (-x) is +0
    assert model.add(8, 23, 1, 0x80000000, 0x80000000) == 0x80000000                     # (-0) + (-0) is -0
    assert model.add(8, 23, 1, 0x00000000, 0x80000000) == 0x00000000                     # (+0) + (-0) is +0
    assert model.add(8, 23, 1, 0x7F800000, 0xFF800000) == qnan32                         # inf - inf is NaN
    assert model.add(8, 23, 1, 0x7F800001, one32) == qnan32                              # a signalling NaN gives the canonical quiet NaN, payload dropped
    assert model.add(8, 23, 1, 0xFFC12345, one32) == qnan32                              # and its sign is dropped
    assert model.add(8, 23, 1, 0x7F7FFFFF, 0x73800000) == 0x7F800000                     # the largest float32 plus half an ulp rounds (ties to even) to infinity
    assert model.add(8, 23, 1, 0x00000001, 0x00000001) == 0x00000002                     # subnormals add exactly
    assert model.add(8, 23, 0, 0x00000001, 0x00000001) == 0x00000000                     # flush to zero: a subnormal is zero
    assert model.add(8, 23, 0, one32, 0x00000001) == one32                               # ... also as a small addend
    assert model.add(8, 23, 0, 0x00800000, 0x80400000) == 0x00800000                     # smallest normal minus a subnormal: the subnormal is read as zero
    assert model.add(8, 23, 0, 0x00800001, 0x80800000) == 0x00000000                     # a difference below the smallest normal number is flushed (+0 sign of the result)
    assert model.add(8, 23, 1, 0x00800001, 0x80800000) == 0x00000001                     # ... but is exact with subnormals
    assert model.add(8, 7, 1, 0x3F80, 0x3F80) == 0x4000                                  # bfloat16: 1.0 + 1.0 = 2.0 (the same top 16 bits as float32)


def test_latency_expressions_match_the_model_table():
    spec = ac.load_spec("fp_add")
    for v, vd in spec["variants"].items():
        for p in vd["exhaustive_points"] + vd["random_points"] + vd["ooc_points"]:
            q = ac.merged_params(spec, v, p)
            assert ac.latency_of(spec, v, q) == model.LATENCY[v](q), (v, q)
