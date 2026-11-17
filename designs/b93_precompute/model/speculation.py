"""Optional arm 4, counted but not built: how often would a send started on the table's most likely outcome be undone?

For every test sample the table holds one class per interval of the late feature (the order-flow imbalance); the late
value then picks the true one. "Most likely" is the class with the largest total weight, where an interval's weight is
how often the late value fell in it on the TRAIN split (no test statistic enters the choice). A speculative send on the
most likely class is undone when the true class differs; a send is only started for the classes an order needs ("up" for
a buy, "down" for a sell). Output: results/b93/speculation.json.

    python -m designs.b93_precompute.model.speculation
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from designs.b87_ml_trading.model import arms as A
from designs.b87_ml_trading.model import lobsim as L
from designs.b89_lutnet_gen.lutgen import model as M89
from designs.b93_precompute.model import gen_rtl as G

ROOT = G.ROOT


def intervals(kind: str):
    if kind == "gbt":
        q = json.loads((G.G87.MODELS / "gbt.json").read_text())
        top = 255
        ths = sorted({max(0, min(x["t"], top)) for t in q["trees"] for x in t["nodes"]
                      if "leaf" not in x and x["f"] == G.LATE and x["t"] >= 0 and max(0, min(x["t"], top)) < top})
        return q, ths
    m = json.loads(G.LG_MODEL.read_text())
    return m, list(m["thresholds"][G.LATE])


def predict(kind, model, X):
    return A.gbt_predict_int(model, X) if kind == "gbt" else M89.twin_predict(model, X)


def main() -> int:
    Xtr, _, _ = L.split("train")
    Xte, _, _ = L.split("test")
    out = {"what": __doc__.split("\n")[0], "late_feature": "order-flow imbalance (packed bits 35:28)", "arms": {}}
    for kind in ("gbt", "lg"):
        model, ths = intervals(kind)
        reps = [ths[i] if i < len(ths) else ths[-1] + 1 for i in range(len(ths) + 1)]
        edges = np.array(ths)
        p = np.bincount(np.searchsorted(edges, Xtr[:, G.LATE], side="left"), minlength=len(reps)).astype(float)
        p /= p.sum()
        tab = np.stack([predict(kind, model, np.where(np.arange(7) == G.LATE, r, Xte)) for r in reps], axis=1)
        true = predict(kind, model, Xte)
        idx = np.searchsorted(edges, Xte[:, G.LATE], side="left")
        assert (tab[np.arange(len(Xte)), idx] == true).all()            # the table reproduces the model
        # weight of each class in a sample's table
        w = np.stack([(tab == k) @ p for k in range(3)], axis=1)
        guess = w.argmax(axis=1)
        distinct = np.array([len(set(r)) for r in tab])
        rec = {"intervals": len(reps), "test_samples": int(len(Xte)),
               "samples_whose_table_has_one_class": float((distinct == 1).mean()),
               "most_likely_class_wrong": float((guess != true).mean()),
               "buy_started": int((guess == 2).sum()), "buy_undone": int(((guess == 2) & (true != 2)).sum()),
               "sell_started": int((guess == 0).sum()), "sell_undone": int(((guess == 0) & (true != 0)).sum())}
        rec["buy_undo_rate"] = rec["buy_undone"] / max(1, rec["buy_started"])
        rec["sell_undo_rate"] = rec["sell_undone"] / max(1, rec["sell_started"])
        out["arms"]["trees" if kind == "gbt" else "lg_small"] = rec
    p = ROOT / "results" / "b93" / "speculation.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1))
    print(json.dumps(out["arms"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
