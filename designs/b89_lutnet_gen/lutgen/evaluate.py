"""Score the frozen brief 89 arms on the brief 87 test split, once, as pre-registered in docs/preregistration.md.

    python -m designs.b89_lutnet_gen.lutgen.evaluate          # -> results/b89/accuracy.json

Per arm and seed: test accuracy per session (10 independent sessions) with a 95% t-interval. For the built seed:
paired per-session differences against the 87 trivial rule, the 87 trees, the 87 MLP (per-session values recorded by
brief 87 on the same test split; the split's digest is checked), and TreeLUT seed 0 (its own integer predictions,
results/b89/treelut/test_predictions.npz).
"""
from __future__ import annotations

import json

import numpy as np

from . import cli as C
from . import data as Dm
from . import model as M

T975_DF9 = 2.262


def per_session(pred, y, g):
    return [float((pred[g == i] == y[g == i]).mean()) for i in range(int(g.max()) + 1)]


def summ(a):
    a = np.asarray(a, dtype=float)
    h = T975_DF9 * a.std(ddof=1) / np.sqrt(len(a))
    return {"mean": round(float(a.mean()), 4), "ci95": [round(float(a.mean() - h), 4), round(float(a.mean() + h), 4)]}


def paired(a, b):
    d = np.asarray(a) - np.asarray(b)
    r = summ(d)
    return {"difference_mean": r["mean"], "ci95": r["ci95"], "a_better": bool(r["ci95"][0] > 0),
            "b_better": bool(r["ci95"][1] < 0)}


def main():
    d = Dm.load(("test",))
    X, y, g = d["test"]
    ref = {"trivial_rule_87": Dm.b87_per_session("imbalance_rule"), "trees_87": Dm.b87_per_session("gbt"),
           "mlp_87": Dm.b87_per_session("mlp"), "lutnet_87": Dm.b87_per_session("lutnet")}
    tl = np.load(C.RES / "treelut" / "test_predictions.npz")
    tl_ps = {s: per_session(tl[f"seed{s}"], y, g) for s in C.SEEDS}
    ref["treelut_seed0"] = tl_ps[0]
    rec = {"schema": "b89-accuracy/1", "test_sha256": Dm.digest(X, y), "interval": "95% t-interval over the 10 test sessions",
           "references": {k: {"per_session": [round(x, 4) for x in v], **summ(v)} for k, v in ref.items()},
           "treelut": {f"seed{s}": summ(v) | {"per_session": [round(x, 4) for x in v]} for s, v in tl_ps.items()},
           "arms": {}}
    for arm in C.frozen()["arms"]:
        bs = C.built_seed(arm)
        runs = []
        for s in C.SEEDS:
            m = C.model_of(arm, s)
            ps = per_session(M.twin_predict(m, X), y, g)
            runs.append({"seed": s, "val": m["val_accuracy"], "test": summ(ps) | {"per_session": [round(x, 4) for x in ps]}})
        b = next(r for r in runs if r["seed"] == bs)["test"]["per_session"]
        rec["arms"][arm] = {"built_seed": bs, "runs": runs,
                            "test_mean_over_seeds": round(float(np.mean([r["test"]["mean"] for r in runs])), 4),
                            "paired_vs": {k: paired(b, v) for k, v in ref.items()}}
        print(arm, bs, [r["test"]["mean"] for r in runs], rec["arms"][arm]["paired_vs"]["trivial_rule_87"])
    (C.RES / "accuracy.json").write_text(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
