"""The brief 87 data, unchanged: same generator, same seeds, same splits. Cached in build/b89/data.npz and checked
against the SHA-256 digests brief 87 recorded in results/b87/accuracy.json, so every number in brief 89 is on exactly
the 87 train, validation and test sets.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "build" / "b89" / "data.npz"
B87_ACC = ROOT / "results" / "b87" / "accuracy.json"


def digest(*arrs) -> str:
    h = hashlib.sha256()
    for a in arrs:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def load(names=("train", "val", "test")) -> dict:
    """{name: (X int64 (N, 7), y int64 (N,), session index (N,))}, digests checked against brief 87."""
    if CACHE.exists():
        z = np.load(CACHE)
        d = {n: (z[f"{n}_X"], z[f"{n}_y"], z[f"{n}_g"]) for n in ("train", "val", "test")}
    else:
        from designs.b87_ml_trading.model import lobsim as L
        d = {n: L.split(n) for n in ("train", "val", "test")}
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        np.savez(CACHE, **{f"{n}_{k}": v for n, t in d.items() for k, v in zip("Xyg", t)})
    ref = json.loads(B87_ACC.read_text())["data_sha256"]
    for n in names:
        X, y, _ = d[n]
        if digest(X, y) != ref[n]:
            raise RuntimeError(f"{n} split differs from brief 87's (digest mismatch); delete {CACHE} and retry")
        g = d[n][2]                    # the session index the paired comparisons rest on (review S8)
        if not np.array_equal(g, np.repeat(np.arange(int(g.max()) + 1), np.bincount(g))) or n == "test" and \
                np.bincount(g).tolist() != [9910] * 10:
            raise RuntimeError(f"{n} split: session index is not the 87 layout")
    return {n: d[n] for n in names}


def b87_per_session(arm: str) -> list[float]:
    """Per-test-session accuracy brief 87 recorded for an arm (seed 0, quantised; or the baseline's test)."""
    a = json.loads(B87_ACC.read_text())["arms"][arm]
    t = a["test"] if "test" in a else a["runs"][0]["test_quantised"]
    return t["per_session"]
