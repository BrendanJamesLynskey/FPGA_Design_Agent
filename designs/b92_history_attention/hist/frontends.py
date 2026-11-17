"""Stage 2 front ends: integer functions of the event stream that make extra columns for the common head.

decay   exponentially decaying sums (shift and add)            -> 8 columns, 0..255
window  the last N token codes                                  -> 4 N columns (each a few bits)
attn    tiny attention over the last N tokens (twin of the RTL) -> 4 columns, 0..15

Every function takes one session (arrays for all its events) and returns one row per event, using only events <= t, with a
zero initial state / zero-padded window (what the fabric holds after a reset). All arithmetic is integer; `>>` is the
arithmetic (floor) shift.
"""
from __future__ import annotations

import numpy as np

from . import tokens as TK

# ---------------------------------------------------------------------------------------------------- decaying sums
CHANNELS = 4                      # ts, sv, ofi, 2*imb-7
RATE_SETS = {"r13": (1, 3), "r24": (2, 4), "r35": (3, 5), "r46": (4, 6)}


def decay_inputs(T: np.ndarray) -> np.ndarray:
    return np.stack([T[:, 0], T[:, 1], T[:, 2], 2 * T[:, 3] - 7], axis=1)


def decay_state(T: np.ndarray, rates) -> np.ndarray:
    """(n, 4 * len(rates)) signed sums s_t = s_{t-1} - (s_{t-1} >> k) + x_t, channel-major then rate."""
    x = decay_inputs(T)
    n = len(x)
    ks = np.array(rates, dtype=np.int64)
    s = np.zeros((CHANNELS, len(ks)), dtype=np.int64)
    out = np.zeros((n, CHANNELS, len(ks)), dtype=np.int64)
    for t in range(n):
        s = s - (s >> ks[None, :]) + x[t][:, None]
        out[t] = s
    return out.reshape(n, -1)


def fit_decay(split, rates) -> dict:
    """Per column: the smallest shift with the training 99.9th percentile of |s >> sh| <= 127."""
    S = split.apply(lambda s: decay_state(s["T"], rates))
    sh = []
    for j in range(S.shape[1]):
        p = float(np.quantile(np.abs(S[:, j]), 0.999))
        k = 0
        while p / (1 << k) > 127:
            k += 1
        sh.append(k)
    return {"rates": list(rates), "shifts": sh}


def decay_cols(s: dict, m: dict) -> np.ndarray:
    S = decay_state(s["T"], m["rates"])
    return np.clip((S >> np.array(m["shifts"], dtype=np.int64)[None, :]) + 128, 0, 255)


# --------------------------------------------------------------------------------------------------------- window
def fit_token_codes(split, bits=(2, 4, 4, 3)) -> dict:
    """Threshold lists per token field (shared by all lags): exact for fields with at most 2^bits values, else quantile cuts."""
    T = np.concatenate([s["T"][s["keep"]] for s in split.sess])
    th = []
    for j in range(4):
        v = T[:, j]
        lo, hi = int(v.min()), int(v.max())
        n = (1 << bits[j]) - 1
        if hi - lo <= n:
            th.append(list(range(lo, hi)))
        else:
            qs = sorted({int(np.quantile(v, (i + 1) / (n + 1))) for i in range(n)})
            th.append([t for t in qs if lo <= t < hi])
    return {"thresholds": th, "bits": list(bits)}


def encode_tokens(T: np.ndarray, m: dict) -> np.ndarray:
    return np.stack([(T[:, j:j + 1] > np.array(t, dtype=np.int64)[None, :]).sum(1) if t else np.zeros(len(T), np.int64)
                     for j, t in enumerate(m["thresholds"])], axis=1)


def window_cols(s: dict, m: dict, n: int) -> np.ndarray:
    """Codes of tokens t, t-1, .., t-n+1 (lag-major), zero for lags before the session start."""
    C = encode_tokens(s["T"], m)
    T_, c = C.shape
    out = np.zeros((T_, n, c), dtype=np.int64)
    for k in range(n):
        out[k:, k, :] = C[:T_ - k]
    return out.reshape(T_, n * c)
