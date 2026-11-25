"""Stimulus helpers of the harness (copied from arith/tools/arith_common.py by arith/tools/gen_harness.py)."""
from __future__ import annotations

import random


def edge_values(w: int) -> list[int]:
    """Values of a w-bit field where arithmetic breaks: 0, 1, 2, the largest and smallest signed, all ones, alternating bits, powers of two."""
    m = (1 << w) - 1
    vals = {0, 1, 2 & m, m, (m - 1) & m, 1 << (w - 1), ((1 << (w - 1)) - 1) & m, ((1 << (w - 1)) + 1) & m, 0x5555555555555555 & m, 0xAAAAAAAAAAAAAAAA & m}
    vals |= {(1 << i) & m for i in range(w)} | {((1 << i) - 1) & m for i in range(1, w + 1)}
    return sorted(vals)


def rand_value(rng: random.Random, w: int, edges: list[int]) -> int:
    """A random w-bit value: a third of the draws are an edge value, a third have a random run of ones or zeros (carry chains), the rest uniform."""
    r = rng.random()
    if r < 0.30:
        return rng.choice(edges)
    if r < 0.60:
        lo = rng.randrange(w)
        hi = rng.randrange(lo, w) + 1
        v = ((1 << (hi - lo)) - 1) << lo
        return v if rng.random() < 0.5 else ((1 << w) - 1) ^ v
    return rng.getrandbits(w)
