"""Per-event tokens and the data for stage 2 (the self-exciting generator).

A token is what the fabric has on the message stream for one event (columns TOK_NAMES):
    ts   trade sign -1, 0, +1                       sv   signed traded size -8..8
    ofi  the event's order-flow term, clipped to -31..31          imb  the 87 imbalance bucket 0..7
`Split` holds every session of a split as full-length arrays (state-carrying front ends run over the whole session from event 0,
with zero initial state, exactly as the fabric would after a reset) and the mask of retained rows (warm-up and unlabelled events
dropped). Nothing here looks at an event after t.
"""
from __future__ import annotations

import numpy as np

from . import prims as P

TOK_NAMES = ["ts", "sv", "ofi", "imb"]
OFI_CLIP = 31
_CACHE: dict = {}


def tokens(X: np.ndarray, Pm: np.ndarray) -> np.ndarray:
    T = np.zeros((len(X), 4), dtype=np.int64)
    T[:, 0] = Pm[:, 0]
    T[:, 1] = Pm[:, 1]
    T[:, 2] = np.clip(Pm[:, 2], -OFI_CLIP, OFI_CLIP)
    T[:, 3] = X[:, 3]
    return T


class Split:
    def __init__(self, gen: str, name: str):
        self.sess = []
        for s in P.SPLITS[gen][name]:
            key = (gen, s)
            if key not in _CACHE:
                r = P.session(gen, s)
                _CACHE[key] = (r["X"].astype(np.int64), tokens(r["X"], r["prims"]), r["y"].astype(np.int64))
            X, T, y = _CACHE[key]
            keep = (np.arange(P.EVENTS) >= P.WARMUP) & (y >= 0)
            self.sess.append({"X": X, "T": T, "y": y, "keep": keep})
        self.y = np.concatenate([s["y"][s["keep"]] for s in self.sess])
        self.g = np.concatenate([np.full(int(s["keep"].sum()), i) for i, s in enumerate(self.sess)])
        self.X = np.concatenate([s["X"][s["keep"]] for s in self.sess])

    def apply(self, fn) -> np.ndarray:
        """fn(session dict) -> (n_events, c) int array; returns the retained rows of all sessions stacked."""
        return np.concatenate([fn(s)[s["keep"]] for s in self.sess])
