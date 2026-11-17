"""The packed port of the stateful arms, and the stream twin.

Port `in_f` (51 bits): bits 37:0 the 87 features packed as in brief 87 (feature 0 in the low bits, widths 8 8 4 3 5 8 2),
then ts + 1 (2 bits, 0..2), sv + 8 (5 bits, 0..16) and ofi + 31 (6 bits, 0..62), where ts, sv, ofi are the trade sign, signed traded
size and the event's order-flow term clipped to -31..31 (tokens.py). The imbalance bucket of the token is feature 3.

`stream_predict(arm, rec, X, PORT)` evaluates the arm's integer function over a stream of events from the reset state, one
prediction per event. That is exactly what the RTL computes (its state is cleared by rst; the first events see zero state).
"""
from __future__ import annotations

import numpy as np

from designs.b89_lutnet_gen.lutgen import model as M89
from designs.b91_lowbit.lowbit import model as M91
from . import frontends as FE
from . import attn as AT

FBITS_CUR = [8, 8, 4, 3, 5, 8, 2]
PORT_BITS = [2, 5, 6]
IN_W = sum(FBITS_CUR) + sum(PORT_BITS)
FLO = [sum(FBITS_CUR[:i]) for i in range(7)]


def pack(X: np.ndarray, PORT: np.ndarray) -> list[int]:
    w = np.zeros(len(X), dtype=object)
    for j in range(7):
        w = w + (X[:, j].astype(object) << FLO[j])
    off = sum(FBITS_CUR)
    for j in range(3):
        w = w + (PORT[:, j].astype(object) << off)
        off += PORT_BITS[j]
    return [int(v) for v in w]


def session_of(X: np.ndarray, PORT: np.ndarray) -> dict:
    T = np.stack([PORT[:, 0] - 1, PORT[:, 1] - 8, PORT[:, 2] - 31, X[:, 3]], axis=1).astype(np.int64)
    return {"X": X.astype(np.int64), "T": T}


def port_of_session(X: np.ndarray, T: np.ndarray) -> np.ndarray:
    return np.stack([T[:, 0] + 1, T[:, 1] + 8, T[:, 2] + 31], axis=1).astype(np.int64)


def random_stream(n: int, seed: int):
    rng = np.random.default_rng(seed)
    X = np.stack([rng.integers(0, 1 << b, size=n) for b in FBITS_CUR], axis=1).astype(np.int64)
    P = np.stack([rng.integers(0, 3, size=n), rng.integers(0, 17, size=n), rng.integers(0, 63, size=n)], axis=1).astype(np.int64)
    return X, P


def columns(arm: str, rec: dict, s: dict) -> np.ndarray:
    front = rec["front"]
    if arm == "a1_decay" or arm == "a4_lut":
        return FE.decay_cols(s, front)
    if arm in ("a2_win16", "a2_win8"):
        return FE.window_cols(s, front, 16 if arm == "a2_win16" else 8)
    if arm in ("a3_top1", "a3_relu"):
        C = M89.encode(front["cth"], s["X"])
        U = AT.window_raw(s["T"])
        return AT.twin(front, C, U)
    return np.zeros((len(s["X"]), 0), dtype=np.int64)


def stream_predict(arm: str, rec: dict, X: np.ndarray, PORT: np.ndarray) -> np.ndarray:
    s = session_of(X, PORT)
    Z = np.concatenate([s["X"], columns(arm, rec, s)], axis=1)
    if arm in ("a4_lut", "ref_lut"):
        return M89.twin_predict(rec["head"], Z)
    return M91.twin_predict(rec["head"], Z)
