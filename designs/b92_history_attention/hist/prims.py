"""Both generators behind one interface, and the history columns.

`session(gen, seed)` returns X (n, 7), prims (n, 3), y (n,), for the 87 generator ("b87") or the self-exciting variant
("hawkes"). `history_columns` builds, for event t, only values of events <= t of the same session (index t - k, k >= 0,
never t + k), and the first `WARMUP` events of a session are dropped, which is more than the longest window.

Families (design.md section 3):
  lagfeat  the 7 features at lags 1..N                     -> 7 + 7 N columns (current features first)
  lagprim  the 3 primitives of events t, t-1, .., t-N+1    -> 7 + 3 N columns (current features first)
"""
from __future__ import annotations

import numpy as np

from designs.b87_ml_trading.model import lobsim as L87
from . import hawkes_sim as H

WARMUP = L87.WARMUP
EVENTS = L87.EVENTS_PER_SESSION
SPLITS = {"b87": L87.SPLITS, "hawkes": H.SPLITS}
NPRIM = 3
MAXN = 16


def session(gen: str, seed: int) -> dict:
    if gen == "b87":
        r = L87.simulate(seed, EVENTS)
        r["prims"] = H.primitives(r["best"], r["events"])
    elif gen == "hawkes":
        r = H.simulate(seed, EVENTS)
    else:
        raise ValueError(gen)
    return r


def lag_stack(A: np.ndarray, n: int) -> np.ndarray:
    """(T, c) -> (T, c * n): columns [A[t], A[t-1], .., A[t-n+1]] per column block; rows t < n-1 use zeros (dropped by
    the warm-up)."""
    T, c = A.shape
    out = np.zeros((T, n, c), dtype=A.dtype)
    for k in range(n):
        out[k:, k, :] = A[:T - k]
    return out.reshape(T, n * c)


def history_columns(X: np.ndarray, P: np.ndarray, family: str, n: int) -> np.ndarray:
    if family == "none":
        return np.zeros((len(X), 0), dtype=np.int32)
    if family == "lagfeat":
        return lag_stack(X, n + 1)[:, X.shape[1]:]          # lags 1..n
    if family == "lagprim":
        return lag_stack(P, n)
    raise ValueError(family)


def build(gen: str, split: str, family: str = "none", n: int = 0, cache: dict | None = None):
    """(X7 | history columns (N, 7 + h), y, session index) of a split, warm-up and unlabelled events dropped."""
    Xs, ys, gs = [], [], []
    for i, s in enumerate(SPLITS[gen][split]):
        key = (gen, s)
        r = cache[key] if cache is not None and key in cache else session(gen, s)
        if cache is not None:
            cache[key] = {"X": r["X"], "prims": r["prims"], "y": r["y"]}
        keep = (np.arange(EVENTS) >= WARMUP) & (r["y"] >= 0)
        Z = np.concatenate([r["X"], history_columns(r["X"], r["prims"], family, n)], axis=1)
        Xs.append(Z[keep])
        ys.append(r["y"][keep].astype(np.int64))
        gs.append(np.full(int(keep.sum()), i))
    return np.concatenate(Xs), np.concatenate(ys), np.concatenate(gs)
