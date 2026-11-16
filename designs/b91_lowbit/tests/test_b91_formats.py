"""Brief 91: the code table, rounding and scale handling of every format against hand-worked values; the CSD terms;
the accumulator bounds; the XNOR-popcount identity for the binary format."""
from __future__ import annotations

import numpy as np
import pytest

from designs.b91_lowbit.lowbit import formats as F
from designs.b91_lowbit.lowbit import model as M


def q(name, vals):
    return F.quantize_np(np.array(vals, dtype=float), F.get(name)).tolist()


def test_code_tables():
    assert F.get("binary").mags == (1,)
    assert F.get("ternary").mags == (0, 1)
    assert F.get("int4").mags == tuple(range(8))
    assert F.get("mxfp4").mags == tuple(int(2 * v) for v in (0, .5, 1, 1.5, 2, 3, 4, 6))     # OCP E2M1 x 2
    assert F.get("log4").mags == (0, 1, 2, 4, 8, 16, 32, 64) and F.get("log4_nz").mags == (1, 2, 4, 8, 16, 32, 64, 128)
    lp = F.get("log4p1").mags
    assert len(lp) == 16 and lp[0] == 0
    assert lp[1:] == tuple(int(2 * 2 ** e * (1 + mm / 2)) for e in range(8) for mm in (0, 1))[:15]   # 1.5 * 2^7 not coded
    assert {f: F.WEIGHT_BITS[f] for f in F.MAGS} == {"binary": 1, "ternary": 2, "int4": 4, "mxfp4": 4, "log4": 4,
                                                      "log4_nz": 4, "log4p1": 5}


def test_binary_rounding():
    assert q("binary", [-3.2, -0.01, 0.0, 0.01, 7]) == [-1, -1, 1, 1, 1]


def test_ternary_rounding_ties_and_saturation():
    assert q("ternary", [-2, -0.6, -0.5, -0.4, 0, 0.5, 0.51, 9]) == [-1, -1, 0, 0, 0, 0, 1, 1]   # tie 0.5: index 0 is even


def test_int4_rounding():
    # ties to the even code index: 0.5 -> 0, 1.5 -> 2, 2.5 -> 2, 6.5 -> 6; saturation at 7; -8 is not a code
    assert q("int4", [0.5, 1.5, 2.5, 6.5, 6.9, 100, -100, -7.6, 3.49]) == [0, 2, 2, 6, 7, 7, -7, -7, 3]


def test_mxfp4_hand_worked():
    # E2M1 values x2: 0 1 2 3 4 6 8 12. In E2M1 units 0.75 is a tie between 0.5 and 1 -> 1 (even mantissa);
    # 2.5 ties 2 and 3 -> 2; 5 ties 4 and 6 -> 4; 0.25 ties 0 and 0.5 -> 0; 7 -> 6; saturation at 6.
    u = [0.25, 0.75, 1.25, 2.5, 3.5, 5.0, 7.0, 100.0]
    got = [v / 2 for v in q("mxfp4", [2 * x for x in u])]
    assert got == [0.0, 1.0, 1.0, 2.0, 4.0, 4.0, 6.0, 6.0]
    assert q("mxfp4", [-2 * 0.6]) == [-1]        # -0.6 in E2M1 units -> -0.5


def test_log4_rounding_zero_and_saturation():
    assert q("log4", [0, 0.4, 0.5, 0.6, 1.4, 1.5, 3.0, 3.01, 50, 96, 97, 1000, -1000]) == \
        [0, 0, 0, 1, 1, 2, 2, 4, 64, 64, 64, 64, -64]
    # linear nearest, not the log-domain midpoint: 1.45 -> 1 (midpoint of 1 and 2 is 1.5); tie 1.5 -> code 2 (even)
    assert q("log4", [1.45, 1.55]) == [1, 2]


def test_log4_nz_has_no_zero():
    assert q("log4_nz", [0.0, 0.1, -0.1, 1.4, 1.6, 1000]) == [1, 1, -1, 1, 2, 128]


def test_log4p1_two_term_levels():
    assert q("log4p1", [0, 0.9, 1.0, 1.1, 2.4, 2.6, 3.4, 3.6, 5.0, 300, -300]) == [0, 0, 0, 2, 2, 3, 3, 4, 6, 256, -256]   # 1.0 ties 0|2 -> code 0; 5.0 ties 4|6 -> code 4 (6)
    # every non-zero level is a sum of at most two powers of two
    for v in F.get("log4p1").mags[1:]:
        assert len(F.csd(v)) <= 2


@pytest.mark.parametrize("n", range(1, 600))
def test_csd_reconstructs_and_is_non_adjacent(n):
    t = F.csd(n)
    assert sum(s * 2 ** d for s, d in t) == n
    ds = sorted(d for _, d in t)
    assert all(b - a >= 2 for a, b in zip(ds, ds[1:]))


def test_every_grid_element_has_at_most_two_terms():
    for name, mags in F.MAGS.items():
        assert all(len(F.csd(v)) <= 2 for v in mags), name


def test_numpy_and_torch_quantisers_agree():
    torch = pytest.importorskip("torch")
    rng = np.random.default_rng(0)
    u = np.concatenate([rng.normal(0, 40, 4000), np.arange(-20, 20.5, 0.25)])
    for name in F.MAGS:
        f = F.get(name)
        assert F.quantize_t(torch.tensor(u), f).numpy().astype(int).tolist() == F.quantize_np(u, f).tolist(), name


def _toy_model(binary=False):
    L1 = {"kind": "hidden", "n": 2, "n_in": 3, "amax": 1 if binary else 15, "W": [[1, -1, 1], [-1, -1, 1]] if binary else [[3, -2, 0], [-7, 4, 1]],
          "sh": [0, 0] if binary else [1, 2], "B": [-1, 1] if binary else [5, -3]}
    L2 = {"kind": "score", "n": 3, "n_in": 2, "W": [[1, 1], [-1, 1], [1, -1]], "sh": [0] * 3, "shmax": 0, "k": [0] * 3, "B": [0, 1, 0]}
    inp = {"kind": "thermo" if binary else "code", "thresholds": [[1, 3], [2], [0, 1, 5]] if binary else [[1, 3, 5, 7], [1, 3, 5, 7], [1, 3, 5, 7]],
           "amax": [1] * 6 if binary else [4, 4, 4]}
    if binary:
        inp["thresholds"] = [[1, 3], [2], [0]]
        inp["amax"] = [1, 1, 1, 1]
        L1["n_in"] = 4
        L1["W"] = [[1, -1, 1, 1], [-1, -1, 1, -1]]
    return {"config": {"fmt": "binary_t3" if binary else "int4", "n_classes": 3, "act_bits": 4}, "input": inp, "layers": [L1, L2]}


def test_twin_by_hand():
    m = _toy_model()
    X = np.array([[4, 0, 8]])
    # codes: 4 -> 2 thresholds exceeded (1,3) = 2; 0 -> 0; 8 -> 4
    x = M.encode_input(m["input"], X)
    assert x.tolist() == [[2, 0, 4]]
    # neuron 0: 3*2 - 2*0 + 0 = 6, (6 + 5) >> 1 = 5; neuron 1: -14 + 0 + 4 = -10, (-10 - 3) >> 2 = -4 -> clipped to 0
    assert M.twin_layers(m, X)[1].tolist() == [[5, 0]]
    assert M.twin_scores(m, X).tolist() == [[5, -5 + 1, 5]]
    assert M.twin_predict(m, X).tolist() == [0]            # tie between class 0 and 2: lowest wins


def test_xnor_popcount_form_equals_integer_form():
    m = _toy_model(binary=True)
    X = np.random.default_rng(1).integers(0, 8, size=(500, 3))
    assert M.twin_predict_xnor(m, X).tolist() == M.twin_predict(m, X).tolist()


def test_bounds_cover_every_input():
    m = _toy_model()
    b = M.bounds(m)
    for lo, hi in b[0]["acc"]:
        assert lo <= hi
    X = np.array([[a, b_, c] for a in range(0, 9, 2) for b_ in range(0, 9, 2) for c in range(0, 9, 2)])
    x = M.encode_input(m["input"], X)
    L = m["layers"][0]
    z = x @ np.array(L["W"]).T + np.array(L["B"])
    for j, (lo, hi) in enumerate(b[0]["acc"]):
        assert lo <= z[:, j].min() and z[:, j].max() <= hi
