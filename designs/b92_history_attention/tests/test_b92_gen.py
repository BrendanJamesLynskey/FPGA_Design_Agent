"""Brief 92 stage 0-1 tests: the generator's primitives agree with the 87 features, the history columns use no event after t,
the splits are disjoint, and the variant is seeded."""
import numpy as np

from designs.b87_ml_trading.model import lobsim as L87
from designs.b92_history_attention.hist import hawkes_sim as H
from designs.b92_history_attention.hist import prims as P


def test_split_seeds_disjoint():
    s = [set(v) for g in P.SPLITS.values() for v in g.values()]
    assert sum(len(x) for x in s) == len(set().union(*s)) == 64


def test_seeded_and_not_the_87_stream():
    a, b = H.simulate(5001, 800), H.simulate(5001, 800)
    assert np.array_equal(a["X"], b["X"]) and np.array_equal(a["prims"], b["prims"])
    assert not np.array_equal(a["X"], L87.simulate(5001, 800)["X"])


def test_primitives_reproduce_the_ofi_and_trade_features():
    for gen in ("b87", "hawkes"):
        r = P.session(gen, 1001 if gen == "b87" else 5001)
        X, Pm = r["X"], r["prims"]
        for t in range(40, 400):
            ofi = int(np.clip(Pm[t - 15:t + 1, 2].sum(), -127, 127)) + 128
            assert X[t, 5] == ofi
        # feature 4 is the sum of the last 8 trade signs (only trades enter the window)
        signs = [int(s) for s in Pm[:, 0] if s]
        k = 0
        for t in range(len(Pm)):
            if Pm[t, 0]:
                k += 1
            if k >= 8 and t > 50:
                last = [int(Pm[u, 0]) for u in range(t + 1) if Pm[u, 0]][-8:]
                assert X[t, 4] == sum(last) + 8
                break
        assert signs


def test_history_uses_only_events_up_to_t():
    r = P.session("hawkes", 5001)
    X, Pm = r["X"], r["prims"]
    t0 = 3000
    X2, P2 = X.copy(), Pm.copy()
    X2[t0 + 1:] += 17          # perturb everything after t0
    P2[t0 + 1:] += 5
    for fam in ("lagfeat", "lagprim"):
        for n in (4, 16):
            a = P.history_columns(X, Pm, fam, n)
            b = P.history_columns(X2, P2, fam, n)
            assert np.array_equal(a[:t0 + 1], b[:t0 + 1])


def test_window_stays_inside_the_session_after_warmup():
    assert P.WARMUP > P.MAXN
    X, y, g = P.build("hawkes", "val", "lagprim", 16)
    assert X.shape[1] == 7 + 48 and len(set(g.tolist())) == 2
    # the first retained row of each session carries real history (no zero padding from the stack)
    r = P.session("hawkes", 6001)
    first = X[g == 0][0]
    assert np.array_equal(first[7:10], r["prims"][P.WARMUP, :])
    assert np.array_equal(first[7 + 45:], r["prims"][P.WARMUP - 15, :])


def test_label_horizon_does_not_cross_the_session_end():
    r = P.session("hawkes", 6001)
    assert (r["y"][-40:] == -1).all() and (r["y"][:-40] >= 0).all()


def test_front_ends_are_causal():
    """Review fix: tokens, decaying sums, window codes and the attention twin at event t do not move when later events change."""
    import json

    from designs.b89_lutnet_gen.lutgen import model as M89
    from designs.b92_history_attention.hist import attn as AT
    from designs.b92_history_attention.hist import frontends as FE
    from designs.b92_history_attention.hist import stage2 as S2
    from designs.b92_history_attention.hist import stream as S
    X, Pm = S.random_stream(600, 5)
    X2, P2 = X.copy(), Pm.copy()
    t0 = 300
    X2[t0 + 1:] = X[::-1][: len(X) - t0 - 1]
    P2[t0 + 1:] = Pm[::-1][: len(X) - t0 - 1]
    a, b = S.session_of(X, Pm), S.session_of(X2, P2)
    if not (S2.RES / "stage2_frozen.json").exists():
        return
    fz = json.loads((S2.RES / "stage2_frozen.json").read_text())
    for arm in ("a1_decay", "a2_win16", "a3_top1", "a3_relu"):
        rec = json.loads(S2.mpath(arm, fz["built_seed"][arm]).read_text())
        ca, cb = S.columns(arm, rec, a), S.columns(arm, rec, b)
        assert np.array_equal(ca[:t0 + 1], cb[:t0 + 1]), arm
