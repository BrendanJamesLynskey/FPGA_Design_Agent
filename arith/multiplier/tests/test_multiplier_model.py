"""The multiplier model (arith/multiplier/model.py) against independent formulations (arith brief 139a)."""
from __future__ import annotations

import itertools
import random

from arith.multiplier import model
from arith.tools import arith_common as ac


def test_model_equals_shift_and_add_exhaustively():
    for wa, wb in [(1, 1), (1, 5), (5, 1), (4, 4), (3, 6), (6, 3), (5, 5), (2, 7)]:
        for sg in (0, 1):
            for a, b in itertools.product(range(1 << wa), range(1 << wb)):
                assert model.mul(wa, wb, sg, a, b) == model.mul_shift_add(wa, wb, sg, a, b), (wa, wb, sg, a, b)


def test_model_equals_python_integers_at_large_widths():
    rng = random.Random(1391)
    for _ in range(3000):
        wa, wb = rng.choice([8, 17, 18, 25, 32, 33, 48]), rng.choice([8, 17, 18, 25, 32, 40])
        a, b = ac.rand_value(rng, wa, ac.edge_values(wa)), ac.rand_value(rng, wb, ac.edge_values(wb))
        assert model.mul(wa, wb, 0, a, b) == a * b
        assert model.mul(wa, wb, 1, a, b) == (model.to_signed(a, wa) * model.to_signed(b, wb)) % (1 << (wa + wb))
        assert model.mul(wa, wb, 1, a, b) == model.mul_shift_add(wa, wb, 1, a, b)


def test_signed_extremes_do_not_overflow_the_full_width_product():
    for wa, wb in [(4, 4), (5, 3), (18, 18)]:
        a, b = 1 << (wa - 1), 1 << (wb - 1)                      # -2**(wa-1) times -2**(wb-1)
        p = model.mul(wa, wb, 1, a, b)
        assert p == 1 << (wa + wb - 2) and model.to_signed(p, wa + wb) == 1 << (wa + wb - 2)


def test_booth_digits_sum_to_the_multiplier_value():
    for wb in range(1, 9):
        for sg in (0, 1):
            for b in range(1 << wb):
                v = model.to_signed(b, wb) if sg else b
                d = model.booth_digits(wb, sg, b)
                assert all(-2 <= x <= 2 for x in d)
                assert sum(x * 4 ** i for i, x in enumerate(d)) == v, (wb, sg, b)
                assert len(d) == (wb + (0 if sg else 1) + 1) // 2


def test_latency_expressions_match_the_model_table():
    spec = ac.load_spec("multiplier")
    for v, vd in spec["variants"].items():
        for p in vd["exhaustive_points"] + vd["random_points"] + vd["ooc_points"]:
            q = ac.merged_params(spec, v, p)
            assert ac.latency_of(spec, v, q) == model.LATENCY[v](q), (v, q)
