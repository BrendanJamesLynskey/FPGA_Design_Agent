"""Stage 0 statistics of both generators on the test sessions -> results/b92/gen_stats.json.

    python -m designs.b92_history_attention.hist.gen_stats

Trade-sign autocorrelation in trade time (lags 1, 2, 5, 10, 20, 50), the autocorrelation of the number of market orders
in blocks of 20 events (block lags 1-5), the market-order share, the clustering of market orders (variance-to-mean ratio of
the block counts; 1 for a Poisson process), and the share of events inside an informed burst (variant only).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import prims as P

ROOT = Path(__file__).resolve().parents[3]
BLOCK = 20


def acf(x: np.ndarray, lags) -> list[float]:
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    d = float((x * x).sum())
    return [round(float((x[:-k] * x[k:]).sum() / d), 4) for k in lags]


def stats(gen: str) -> dict:
    sign_acf, cnt_acf, share, vmr, bshare = [], [], [], [], []
    for s in P.SPLITS[gen]["test"]:
        r = P.session(gen, s)
        sg = r["prims"][P.WARMUP:, 0]
        tr = sg[sg != 0]
        sign_acf.append(acf(tr, (1, 2, 5, 10, 20, 50)))
        n = len(sg) // BLOCK
        c = (sg[:n * BLOCK] != 0).reshape(n, BLOCK).sum(1)
        cnt_acf.append(acf(c, (1, 2, 3, 4, 5)))
        share.append(float((sg != 0).mean()))
        vmr.append(float(c.var() / c.mean()))
        if "burst" in r:
            bshare.append(float((r["burst"] != 0).mean()))
    m = lambda a: [round(float(v), 4) for v in np.mean(a, axis=0)]  # noqa: E731
    out = {"sessions": len(P.SPLITS[gen]["test"]), "market_share": round(float(np.mean(share)), 4),
           "block_count_variance_to_mean": round(float(np.mean(vmr)), 3), "block": BLOCK,
           "trade_sign_acf": dict(zip((1, 2, 5, 10, 20, 50), m(sign_acf))),
           "block_count_acf": dict(zip((1, 2, 3, 4, 5), m(cnt_acf)))}
    if bshare:
        out["burst_share_of_events"] = round(float(np.mean(bshare)), 4)
    return out


def main():
    rec = {"schema": "b92-gen-stats/1", "b87": stats("b87"), "hawkes": stats("hawkes")}
    p = ROOT / "results" / "b92"
    p.mkdir(parents=True, exist_ok=True)
    (p / "gen_stats.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
