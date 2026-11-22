"""The adder model (arith/adder/model.py) against independent formulations (arith brief 139a)."""
from __future__ import annotations

import itertools
import random

from arith.adder import model
from arith.tools import arith_common as ac


def test_model_equals_bit_serial_formulation_exhaustively():
    for w in range(1, 7):
        for a, b, c, s in itertools.product(range(1 << w), range(1 << w), (0, 1), (0, 1)):
            assert model.addsub(w, a, b, c, s) == model.addsub_bitserial(w, a, b, c, s), (w, a, b, c, s)


def test_model_equals_python_integers_at_large_widths():
    rng = random.Random(139)
    for _ in range(4000):
        w = rng.choice([8, 16, 31, 32, 33, 48, 64, 65, 100, 128])
        edges = ac.edge_values(w)
        a, b = ac.rand_value(rng, w, edges), ac.rand_value(rng, w, edges)
        c, sub = rng.getrandbits(1), rng.getrandbits(1)
        assert model.addsub(w, a, b, c, sub) == model.addsub_bitserial(w, a, b, c, sub), (w, a, b, c, sub)
        s, co, _ = model.addsub(w, a, b, c, sub)
        full = (a - b - c) if sub else (a + b + c)
        assert s == full % (1 << w)
        assert co == (int(full >= 0) if sub else full >> w)


def test_model_conventions_are_the_documented_ones():
    # co with sub = 1 is 1 when there is NO borrow; cin is a borrow in when sub = 1; ovf is the signed flag
    assert model.addsub(8, 5, 3, 0, 1) == (2, 1, 0)
    assert model.addsub(8, 3, 5, 0, 1) == (254, 0, 0)
    assert model.addsub(8, 5, 5, 1, 1) == (255, 0, 0)          # 5 - 5 - 1 borrows
    assert model.addsub(8, 255, 1, 0, 0) == (0, 1, 0)
    assert model.addsub(8, 127, 1, 0, 0) == (128, 0, 1)        # signed overflow without a carry out
    assert model.addsub(8, 128, 1, 0, 1) == (127, 1, 1)        # -128 - 1 overflows
    assert model.addsub(1, 1, 1, 0, 0) == (0, 1, 1)            # -1 + -1 at width 1
    assert model.addsub(1, 0, 0, 1, 0) == (1, 0, 1)            # 0 + 0 + 1 is outside -1..0


def test_latency_expressions_match_the_model_table():
    spec = ac.load_spec("adder")
    for v, vd in spec["variants"].items():
        for p in vd["exhaustive_points"] + vd["random_points"] + vd["ooc_points"]:
            q = ac.merged_params(spec, v, p)
            assert ac.latency_of(spec, v, q) == model.LATENCY[v](q), (v, q)
