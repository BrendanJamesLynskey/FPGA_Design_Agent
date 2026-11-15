"""Seeded synthetic order flow, the integer features the fabric computes, and the label.

Everything here is synthetic: no exchange, no market data. The microstructure model (docs/data_model.md has the full
description and the parameters):

- one instrument, prices in integer ticks; a book of K price levels a side, each a queue size in lots;
- a hidden value v (in ticks) follows a random walk with occasional jumps; nobody sees it;
- each event is one of: a limit order added to a level (or inside the spread), a cancel from a level, or a market
  order that takes liquidity from the best level. The event mix and the sides are tilted towards v - mid by a
  logistic "informed" weight, so the order flow carries information about where the mid will go;
- when the best queue empties the best price moves one tick away and a fresh level appears at the back.

Features (all integers, computed after each event exactly as rtl/ml_feat.sv computes them):

  f0 bid size at the best bid, saturated to 255         f1 ask size at the best ask, saturated to 255
  f2 spread in ticks, saturated to 15                   f3 queue imbalance bucket 0..7 (seven ratio comparisons)
  f4 sum of the last 8 trade signs + 8 (0..16)          f5 order-flow imbalance over the last 16 events, clipped
                                                           to -127..127, + 128 (1..255)
  f6 direction of the last mid change (0 down, 1 none yet, 2 up)

Label: the sign of the mid-price change H events later (0 down, 1 unchanged, 2 up).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np

FEATURES = ["bid_sz", "ask_sz", "spread", "imb_bucket", "trade_sign_sum", "ofi16", "last_mid_dir"]
FEATURE_BITS = [8, 8, 4, 3, 5, 8, 2]
CLASSES = ["down", "flat", "up"]


@dataclass(frozen=True)
class Params:
    levels: int = 5               # K price levels a side
    mean_queue: float = 15.0      # mean size of a freshly revealed level (lots, geometric)
    p_market: float = 0.12        # event mix: market order, limit add, cancel (the rest)
    p_add: float = 0.48
    p_inside: float = 0.9         # a limit add that lands inside a spread wider than one tick
    max_market: int = 8           # market order size uniform 1..max_market lots
    max_add: int = 6              # limit order size uniform 1..max_add lots
    sigma_v: float = 0.06         # random-walk step of the hidden value (ticks per event)
    p_jump: float = 0.002         # chance per event of a jump of +/- jump_ticks in v
    jump_ticks: float = 3.0
    informed: float = 1.6         # logistic weight on (v - mid) for the side of each event
    horizon: int = 40             # label horizon H in events


def imb_bucket(b: int, a: int) -> int:
    """Seven ratio comparisons, each a shift-and-add compare in the fabric; monotone in b / a."""
    return int(4 * b > a) + int(2 * b > a) + int(3 * b > 2 * a) + int(b > a) + int(2 * b > 3 * a) + int(b > 2 * a) \
        + int(b > 4 * a)


def ofi_event(pb0: int, qb0: int, pa0: int, qa0: int, pb1: int, qb1: int, pa1: int, qa1: int) -> int:
    """Order-flow imbalance of one event from the best levels before (0) and after (1), as in Cont, Kukanov and
    Stoikov (2014); clipped to -127..127."""
    e = (qb1 if pb1 >= pb0 else 0) - (qb0 if pb1 <= pb0 else 0) - (qa1 if pa1 <= pa0 else 0) + (qa0 if pa1 >= pa0 else 0)
    return max(-127, min(127, e))


class FeatureState:
    """The fabric's feature state: the previous best levels, the last 8 trade signs, the last 16 OFI terms and the
    direction of the last mid change. `update` is called after each event with the new best levels."""

    def __init__(self, pb: int, qb: int, pa: int, qa: int):
        self.prev = (pb, qb, pa, qa)
        self.trades = [0] * 8          # +1 buy aggressor, -1 sell, 0 empty (reset)
        self.ofi = [0] * 16
        self.last_dir = 1

    def update(self, pb: int, qb: int, pa: int, qa: int, trade_sign: int) -> list[int]:
        pb0, qb0, pa0, qa0 = self.prev
        self.ofi = self.ofi[1:] + [ofi_event(pb0, qb0, pa0, qa0, pb, qb, pa, qa)]
        if trade_sign:
            self.trades = self.trades[1:] + [trade_sign]
        dm = (pb + pa) - (pb0 + pa0)
        if dm > 0:
            self.last_dir = 2
        elif dm < 0:
            self.last_dir = 0
        self.prev = (pb, qb, pa, qa)
        return self.features()

    def features(self) -> list[int]:
        pb, qb, pa, qa = self.prev
        b = 0 if pb == 0 else min(qb, 255)            # an empty side (price 0; only in the 58A book) has size 0
        a = 0 if pa == 0 else min(qa, 255)
        spread = 15 if (pb == 0 or pa == 0 or pa < pb) else min(pa - pb, 15)
        ofi = max(-127, min(127, sum(self.ofi)))
        return [b, a, spread, imb_bucket(b, a), sum(self.trades) + 8, ofi + 128, self.last_dir]


def simulate(seed: int, n_events: int, p: Params = Params()) -> dict:
    """One session of n_events events. Returns features X (n, 7) int, the mid in half ticks, the event log and the
    label y (n,) for every event that has H events after it (the last H events get y = -1)."""
    rng = np.random.default_rng(seed)
    K = p.levels
    newq = lambda: int(rng.geometric(1.0 / p.mean_queue))  # noqa: E731
    pb, pa = 10_000, 10_001
    bq = [newq() for _ in range(K)]
    aq = [newq() for _ in range(K)]
    v = (pb + pa) / 2.0
    fs = FeatureState(pb, bq[0], pa, aq[0])
    X = np.zeros((n_events, 7), dtype=np.int32)
    mid2 = np.zeros(n_events, dtype=np.int64)
    best = np.zeros((n_events, 4), dtype=np.int64)     # best bid price, bid size, best ask price, ask size
    events = []                     # (kind, side, price, size): kind ADD/CANCEL/TRADE, side 0 bid / 1 ask
    for t in range(n_events):
        v += p.sigma_v * rng.standard_normal()
        if rng.random() < p.p_jump:
            v += p.jump_ticks * (1 if rng.random() < 0.5 else -1)
        mid = (pb + pa) / 2.0
        w = 1.0 / (1.0 + math.exp(-p.informed * (v - mid)))   # weight towards buying pressure
        u = rng.random()
        trade_sign = 0
        if u < p.p_market:
            buy = rng.random() < w
            size = int(rng.integers(1, p.max_market + 1))
            trade_sign = 1 if buy else -1
            q = aq if buy else bq
            px = pa if buy else pb
            events.append(("TRADE", 1 if buy else 0, px, min(size, q[0])))
            q[0] -= size
            while q[0] <= 0:                     # the level is gone: the best price moves away, a new level at the back
                left = -q[0]
                q.pop(0)
                q.append(newq())
                if buy:
                    pa += 1
                else:
                    pb -= 1
                if left == 0:
                    break
                q[0] -= left
        elif u < p.p_market + p.p_add:
            bid = rng.random() < w                # buying pressure adds bids
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
            bid = rng.random() >= w               # buying pressure pulls asks: cancel on the ask side
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
        X[t] = fs.update(pb, bq[0], pa, aq[0], trade_sign)
        mid2[t] = pb + pa
        best[t] = (pb, bq[0], pa, aq[0])
    H = p.horizon
    y = np.full(n_events, -1, dtype=np.int8)
    d = mid2[H:] - mid2[:-H]
    y[:-H] = np.where(d > 0, 2, np.where(d < 0, 0, 1))
    return {"X": X, "mid2": mid2, "best": best, "y": y, "events": events, "params": asdict(p), "seed": seed}


# Fixed splits by seed. Each split is a set of independent sessions, so no label window crosses a split and the
# test sessions never share a random stream with training.
SPLITS = {
    "train": [1001 + i for i in range(20)],
    "val": [2001 + i for i in range(2)],
    "test": [3001 + i for i in range(10)],
}
EVENTS_PER_SESSION = 10_000
WARMUP = 50                  # events dropped at the start of each session (the trade and OFI windows fill)


def split(name: str, p: Params = Params()) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Features, labels and the session index of every usable event of a split."""
    Xs, ys, gs = [], [], []
    for i, s in enumerate(SPLITS[name]):
        r = simulate(s, EVENTS_PER_SESSION, p)
        keep = np.arange(EVENTS_PER_SESSION) >= WARMUP
        keep &= r["y"] >= 0
        Xs.append(r["X"][keep])
        ys.append(r["y"][keep].astype(np.int64))
        gs.append(np.full(int(keep.sum()), i))
    return np.concatenate(Xs), np.concatenate(ys), np.concatenate(gs)
