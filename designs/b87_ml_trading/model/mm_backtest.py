"""A small market-making back-test on the test sessions: the no-ML baseline and the same quoting rule with each arm's
direction forecast added as a short-term signal.

The baseline is our own implementation, in our own words, of the idea of the at-the-touch market maker with a running
inventory penalty in Cartea, Jaimungal and Penalva, *Algorithmic and High-Frequency Trading* (2015), chapter 10
(market making), reduced to a one-step (myopic) rule:

    post a one-lot bid at the best bid  iff  (mid - bid) + alpha * d - phi * ((q + 1)^2 - q^2) > 0
    post a one-lot ask at the best ask  iff  (ask - mid) - alpha * d - phi * ((q - 1)^2 - q^2) > 0

with q the inventory, phi the inventory penalty and d in {-1, 0, +1} the forecast direction (0 for the no-ML rule).
This is not the book's closed-form solution (no horizon, no fill-rate model); it keeps its structure: half the spread
earned against an inventory cost, and, in the signal version, the book's "short-term alpha" term.

Fill model (assumed, illustrative): our order joins the back of the best queue; a market order of size m on our side
fills us with probability min(1, m / (queue + 1)). The inventory is marked to the final mid. Units: ticks.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import arms as A
from . import lobsim as L

PHI = 0.02          # inventory penalty, ticks per lot^2 (fixed before the run, not tuned)
ALPHA = 1.0         # weight of the direction forecast, ticks (fixed before the run, not tuned)
QMAX = 20


def run_session(sess: dict, d: np.ndarray, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    best, ev = sess["best"], sess["events"]
    q, cash, fills = 0, 0.0, 0
    for t in range(L.WARMUP, len(ev) - 1):
        pb, qb, pa, qa = best[t]
        mid = (pb + pa) / 2.0
        post_b = q < QMAX and (mid - pb) + ALPHA * d[t] - PHI * (2 * q + 1) > 0
        post_a = q > -QMAX and (pa - mid) - ALPHA * d[t] - PHI * (-2 * q + 1) > 0
        kind, side, px, size = ev[t + 1]
        if kind != "TRADE":
            continue
        if side == 0 and post_b and rng.random() < min(1.0, size / (qb + 1)):      # a seller hits the bid
            q, cash, fills = q + 1, cash - pb, fills + 1
        elif side == 1 and post_a and rng.random() < min(1.0, size / (qa + 1)):    # a buyer lifts the ask
            q, cash, fills = q - 1, cash + pa, fills + 1
    pnl = cash + q * sess["mid2"][-1] / 2.0
    return {"pnl_ticks": round(pnl, 2), "fills": fills, "final_inventory": q}


def run_all(models: Path, rec: dict) -> dict:
    rule = json.loads((models / "imbalance_rule.json").read_text())
    gbt = json.loads((models / "gbt.json").read_text())
    mlp = json.loads((models / "mlp.json").read_text())
    lut = json.loads((models / "lutnet.json").read_text())
    signals = {"none (no-ML rule)": lambda X: np.zeros(len(X)),
               "imbalance_rule": lambda X: A.imbalance_rule_predict(rule, X) - 1,
               "gbt": lambda X: A.gbt_predict_int(gbt, X) - 1,
               "mlp": lambda X: A.mlp_predict_int(mlp, X) - 1,
               "lutnet": lambda X: A.lut_predict_int(lut, X) - 1}
    res = {k: [] for k in signals}
    for i, s in enumerate(L.SPLITS["test"]):
        sess = L.simulate(s, L.EVENTS_PER_SESSION)
        for k, f in signals.items():
            res[k].append(run_session(sess, f(sess["X"]), seed=10_000 + i))
    out = {"what": __doc__.strip().splitlines()[0], "phi": PHI, "alpha": ALPHA, "qmax": QMAX,
           "fill_model": "back of the best queue; fill probability min(1, m / (queue + 1)); illustrative",
           "arms": {}}
    base = np.array([r["pnl_ticks"] for r in res["none (no-ML rule)"]])
    for k, rs in res.items():
        p = np.array([r["pnl_ticks"] for r in rs])
        d = p - base
        h = 2.262 * d.std(ddof=1) / np.sqrt(len(d)) if k != "none (no-ML rule)" else 0.0
        hp = 2.262 * p.std(ddof=1) / np.sqrt(len(p))
        out["arms"][k] = {"pnl_per_session_mean": round(float(p.mean()), 1),
                          "pnl_ci95": [round(float(p.mean() - hp), 1), round(float(p.mean() + hp), 1)],
                          "minus_no_ml_mean": round(float(d.mean()), 1),
                          "minus_no_ml_ci95": [round(float(d.mean() - h), 1), round(float(d.mean() + h), 1)],
                          "fills_mean": round(float(np.mean([r["fills"] for r in rs])), 1),
                          "sessions": rs}
    return out
