"""Train every arm (three training seeds), quantise, and score on the test split; write the models the RTL is
generated from (seed 0) and the accuracy record.

    python3 -m designs.b87_ml_trading.model.evaluate --out results/b87

Intervals: each test session is an independent simulated session, so the interval is a 95% t-interval over the 10
per-session accuracies (events inside one session are correlated; pooling them would overstate the precision).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from . import arms as A
from . import lobsim as L
from . import mm_backtest as MB

SEEDS = (0, 1, 2)
T975_DF9 = 2.262            # Student t, 97.5th percentile, 9 degrees of freedom (10 test sessions)


def per_session(pred, y, g) -> list[float]:
    return [float((pred[g == i] == y[g == i]).mean()) for i in range(int(g.max()) + 1)]


def summary(accs: list[float]) -> dict:
    a = np.array(accs)
    m, s = float(a.mean()), float(a.std(ddof=1))
    h = T975_DF9 * s / np.sqrt(len(a))
    return {"mean": round(m, 4), "ci95": [round(m - h, 4), round(m + h, 4)], "per_session": [round(x, 4) for x in a]}


def digest(*arrs) -> str:
    h = hashlib.sha256()
    for a in arrs:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/b87")
    args = ap.parse_args()
    out = Path(args.out)
    (out / "models").mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    Xtr, ytr, _ = L.split("train")
    Xv, yv, _ = L.split("val")
    Xte, yte, gte = L.split("test")
    rec = {"schema": "b87-accuracy/1",
           "splits": {k: {"seeds": v, "events_per_session": L.EVENTS_PER_SESSION, "warmup": L.WARMUP} for k, v in
                      L.SPLITS.items()},
           "sizes": {"train": len(ytr), "val": len(yv), "test": len(yte)},
           "class_share_test": (np.bincount(yte, minlength=3) / len(yte)).round(4).tolist(),
           "data_sha256": {"train": digest(Xtr, ytr), "val": digest(Xv, yv), "test": digest(Xte, yte)},
           "interval": "95% t-interval over the 10 test sessions (t = 2.262, 9 df)",
           "arms": {}}
    from dataclasses import asdict
    rec["params"] = asdict(L.Params())

    maj = int(np.bincount(ytr).argmax())
    rec["arms"]["majority"] = {"what": f"always class {maj} (the most common class in train)",
                               "test": summary(per_session(np.full(len(yte), maj), yte, gte))}
    rule = A.imbalance_rule_fit(Xv, yv)
    (out / "models" / "imbalance_rule.json").write_text(json.dumps(rule, indent=1))
    rec["arms"]["imbalance_rule"] = {"what": "up if imbalance bucket >= hi, down if <= lo, else flat; tuned on val",
                                     "fit": rule, "test": summary(per_session(A.imbalance_rule_predict(rule, Xte),
                                                                              yte, gte))}

    for name in ("gbt", "mlp", "lutnet"):
        runs = []
        for s in SEEDS:
            if name == "gbt":
                m = A.gbt_fit(Xtr, ytr, s)
                q = A.gbt_quantise(m)
                pf, pq = m.predict(Xte), A.gbt_predict_int(q, Xte)
                pv = A.gbt_predict_int(q, Xv)
            elif name == "mlp":
                r = A.mlp_fit(Xtr, ytr, Xv, yv, s)
                q = r["int"]
                pf, pq = A.mlp_float_predict(r["float"], Xte), A.mlp_predict_int(q, Xte)
                pv = A.mlp_predict_int(q, Xv)
            else:
                q = A.lut_fit(Xtr, ytr, Xv, yv, s)
                pf = pq = A.lut_predict_int(q, Xte)     # the LUT network has no separate float model at inference
                pv = A.lut_predict_int(q, Xv)
            runs.append({"seed": s, "test_float": summary(per_session(pf, yte, gte)),
                         "test_quantised": summary(per_session(pq, yte, gte)),
                         "val_quantised": round(float((pv == yv).mean()), 4),
                         "agreement_quantised_vs_float": round(float((pf == pq).mean()), 4)})
            if s == 0:
                (out / "models" / f"{name}.json").write_text(json.dumps(q))
            print(name, s, runs[-1]["test_quantised"]["mean"], runs[-1]["test_float"]["mean"], flush=True)
        rec["arms"][name] = {"runs": runs,
                             "seed0_used_for_rtl": True,
                             "test_quantised_mean_over_seeds": round(float(np.mean(
                                 [r["test_quantised"]["mean"] for r in runs])), 4)}
    base = rec["arms"]["imbalance_rule"]["test"]
    for name in ("gbt", "mlp", "lutnet"):
        r0 = rec["arms"][name]["runs"][0]["test_quantised"]
        d = np.array(r0["per_session"]) - np.array(base["per_session"])
        h = T975_DF9 * d.std(ddof=1) / np.sqrt(len(d))
        rec["arms"][name]["vs_imbalance_rule_seed0"] = {
            "paired_difference_mean": round(float(d.mean()), 4),
            "ci95": [round(float(d.mean() - h), 4), round(float(d.mean() + h), 4)],
            "beats_trivial_rule": bool(d.mean() - h > 0)}
    rec["backtest"] = MB.run_all(out / "models", rec)
    rec["seconds"] = round(time.time() - t0, 1)
    (out / "accuracy.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps({k: (v.get("test") or v.get("test_quantised_mean_over_seeds")) for k, v in rec["arms"].items()},
                     indent=1))


if __name__ == "__main__":
    main()
