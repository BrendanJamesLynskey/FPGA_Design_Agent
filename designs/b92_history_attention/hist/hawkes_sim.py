"""Brief 92 stage 0: the self-exciting variant of the brief 87 order-flow generator.

The book mechanics, the hidden value's random walk and jumps, the "informed" logistic tilt, the features and the label are
the brief 87 ones (designs/b87_ml_trading/model/lobsim.py, unchanged and still the comparison). Three history mechanisms
are added; docs/design.md section 2 states them with the reasons:

  A  self-exciting arrivals: P(market order at event t) = min(0.5, mu + A_t); a market order does A <- rho A + alpha,
     any other event A <- rho A; rho = 1 - 1/tau_e. Branching ratio n = alpha tau_e.
  B  sign persistence: S <- rho_s S (+ sign on a market order); the buy logit of a market order gets + gamma S.
  C  informed bursts: a hidden b in {-1, 0, +1}; while on, the buy logit gets + beta_b b and the hidden value moves
     d_b b per event; and every market order moves the hidden value by kappa sign size (permanent impact).

`simulate` returns the 87 dictionary plus `prims`, the per-event primitives the fabric sees on the message stream, and
`burst` (the hidden state, for diagnostics only; no model reads it).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np

from designs.b87_ml_trading.model import lobsim as L87

PRIM_NAMES = ["trade_sign", "signed_size", "ofi_event"]


@dataclass(frozen=True)
class HParams:
    base: L87.Params = L87.Params()
    mu: float = 0.06              # baseline market-order probability
    tau_e: float = 16.0           # excitation kernel decay (events)
    n_branch: float = 0.5         # branching ratio alpha * tau_e (< 1: stationary)
    tau_s: float = 24.0           # sign-memory decay (events)
    gamma: float = 0.25           # buy-logit weight on the decayed sign sum
    p_burst: float = 0.004        # chance per event that an informed burst starts
    burst_len: float = 40.0       # mean burst length (events, geometric)
    beta_b: float = 1.5           # buy-logit weight of the burst direction
    d_b: float = 0.03             # hidden-value drift per event during a burst (ticks)
    kappa: float = 0.01           # permanent impact of a market order on the hidden value (ticks per lot)

    @property
    def alpha(self) -> float:
        return self.n_branch / self.tau_e

    def to_dict(self):
        return asdict(self)


# Fixed splits by seed, disjoint from the 87 seeds (1001-1020, 2001-2002, 3001-3010); same sizes.
SPLITS = {"train": [5001 + i for i in range(20)], "val": [6001 + i for i in range(2)], "test": [7001 + i for i in range(10)]}


def primitives(best: np.ndarray, events: list) -> np.ndarray:
    """(n, 3) int: trade sign (+1 buy aggressor, -1 sell, 0 not a trade), signed traded size, and the event's own
    order-flow term (Cont, Kukanov and Stoikov), clipped to -127..127, from the best levels before and after. Event 0 has
    no earlier book and gets 0 (it is inside the dropped warm-up)."""
    n = len(events)
    P = np.zeros((n, 3), dtype=np.int32)
    for t, (kind, side, _px, size) in enumerate(events):
        if kind == "TRADE":
            s = 1 if side == 1 else -1
            P[t, 0], P[t, 1] = s, s * size
        if t:
            pb0, qb0, pa0, qa0 = (int(v) for v in best[t - 1])
            pb1, qb1, pa1, qa1 = (int(v) for v in best[t])
            P[t, 2] = L87.ofi_event(pb0, qb0, pa0, qa0, pb1, qb1, pa1, qa1)
    return P


def simulate(seed: int, n_events: int, hp: HParams = HParams()) -> dict:
    p = hp.base
    rng = np.random.default_rng(seed)
    K = p.levels
    newq = lambda: int(rng.geometric(1.0 / p.mean_queue))  # noqa: E731
    pb, pa = 10_000, 10_001
    bq = [newq() for _ in range(K)]
    aq = [newq() for _ in range(K)]
    v = (pb + pa) / 2.0
    fs = L87.FeatureState(pb, bq[0], pa, aq[0])
    rho, rho_s, alpha = 1.0 - 1.0 / hp.tau_e, 1.0 - 1.0 / hp.tau_s, hp.alpha
    A, S, b, left = 0.0, 0.0, 0, 0
    p_add_rest = p.p_add / (1.0 - p.p_market)       # of the non-market events, the share that are limit adds
    X = np.zeros((n_events, 7), dtype=np.int32)
    mid2 = np.zeros(n_events, dtype=np.int64)
    best = np.zeros((n_events, 4), dtype=np.int64)
    burst = np.zeros(n_events, dtype=np.int8)
    events = []
    for t in range(n_events):
        # hidden burst state
        if b == 0:
            if rng.random() < hp.p_burst:
                b = 1 if rng.random() < 0.5 else -1
                left = int(rng.geometric(1.0 / hp.burst_len))
        else:
            left -= 1
            if left <= 0:
                b = 0
        v += p.sigma_v * rng.standard_normal() + hp.d_b * b
        if rng.random() < p.p_jump:
            v += p.jump_ticks * (1 if rng.random() < 0.5 else -1)
        mid = (pb + pa) / 2.0
        gap = p.informed * (v - mid)
        w = 1.0 / (1.0 + math.exp(-gap))
        pm = min(0.5, hp.mu + A)
        u = rng.random()
        trade_sign = 0
        if u < pm:
            wm = 1.0 / (1.0 + math.exp(-(gap + hp.gamma * S + hp.beta_b * b)))
            buy = rng.random() < wm
            size = int(rng.integers(1, p.max_market + 1))
            trade_sign = 1 if buy else -1
            q = aq if buy else bq
            px = pa if buy else pb
            events.append(("TRADE", 1 if buy else 0, px, min(size, q[0])))
            v += hp.kappa * trade_sign * min(size, q[0])
            q[0] -= size
            while q[0] <= 0:
                lft = -q[0]
                q.pop(0)
                q.append(newq())
                if buy:
                    pa += 1
                else:
                    pb -= 1
                if lft == 0:
                    break
                q[0] -= lft
        elif rng.random() < p_add_rest:
            bid = rng.random() < w
            size = int(rng.integers(1, p.max_add + 1))
            if pa - pb > 1 and rng.random() < p.p_inside:
                if bid:
                    pb += 1
                    bq.insert(0, size)
                    bq.pop()
                else:
                    pa -= 1
                    aq.insert(0, size)
                    aq.pop()
                events.append(("ADD", 0 if bid else 1, pb if bid else pa, size))
            else:
                lvl = min(int(rng.geometric(0.45)) - 1, K - 1)
                (bq if bid else aq)[lvl] += size
                events.append(("ADD", 0 if bid else 1, (pb - lvl) if bid else (pa + lvl), size))
        else:
            bid = rng.random() >= w
            q = bq if bid else aq
            tot = sum(q)
            if tot > 0:
                r = rng.integers(0, tot)
                lvl = 0
                while r >= q[lvl]:
                    r -= q[lvl]
                    lvl += 1
                size = min(q[lvl], int(rng.integers(1, p.max_add + 1)))
                q[lvl] -= size
                events.append(("CANCEL", 0 if bid else 1, (pb - lvl) if bid else (pa + lvl), size))
                if lvl == 0 and q[0] == 0:
                    q.pop(0)
                    q.append(newq())
                    if bid:
                        pb -= 1
                    else:
                        pa += 1
            else:
                events.append(("CANCEL", 0 if bid else 1, pb if bid else pa, 0))
        A = rho * A + (alpha if trade_sign else 0.0)
        S = rho_s * S + trade_sign
        X[t] = fs.update(pb, bq[0], pa, aq[0], trade_sign)
        mid2[t] = pb + pa
        best[t] = (pb, bq[0], pa, aq[0])
        burst[t] = b
    H = p.horizon
    y = np.full(n_events, -1, dtype=np.int8)
    d = mid2[H:] - mid2[:-H]
    y[:-H] = np.where(d > 0, 2, np.where(d < 0, 0, 1))
    return {"X": X, "mid2": mid2, "best": best, "y": y, "events": events, "params": hp.to_dict(), "seed": seed,
            "prims": primitives(best, events), "burst": burst}
