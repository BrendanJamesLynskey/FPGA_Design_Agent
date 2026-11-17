"""Score the frozen brief 91 networks on the brief 87 test split, once, as pre-registered in docs/preregistration.md.

    python -m designs.b91_lowbit.lowbit.evaluate          # -> results/b91/accuracy.json

Per network and seed: test accuracy per session (10 independent sessions) with a 95% t-interval. For the built seed:
paired per-session differences against the 87 trivial rule, trees and MLP, the 89 networks lg_add, lg_small, lg_b87
(built seeds) and TreeLUT seed 0 (all per-session values recorded by briefs 87 and 89 on the same test split).
"""
from __future__ import annotations

import json

import numpy as np

from designs.b89_lutnet_gen.lutgen import data as Dm
from designs.b89_lutnet_gen.lutgen.evaluate import paired, per_session, summ
from . import cli as C
from . import model as M


def refs() -> dict:
    a89 = json.loads((Dm.ROOT / "results" / "b89" / "accuracy.json").read_text())
    r = {"trivial_rule_87": Dm.b87_per_session("imbalance_rule"), "trees_87": Dm.b87_per_session("gbt"),
         "mlp_87": Dm.b87_per_session("mlp"), "treelut_seed0": a89["treelut"]["seed0"]["per_session"]}
    for arm, a in a89["arms"].items():
        r[arm] = next(x for x in a["runs"] if x["seed"] == a["built_seed"])["test"]["per_session"]
    return r


def main():
    X, y, g = Dm.load(("test",))["test"]
    ref = refs()
    rec = {"schema": "b91-accuracy/1", "test_sha256": Dm.digest(X, y),
           "interval": "95% t-interval over the 10 test sessions",
           "references": {k: {"per_session": [round(x, 4) for x in v], **summ(v)} for k, v in ref.items()}, "networks": {}}
    for net in C.frozen()["networks"]:
        runs = []
        for s in C.SEEDS:
            m = C.model_of(net, s)
            ps = per_session(M.twin_predict(m, X), y, g)
            runs.append({"seed": s, "val": m["val_accuracy"], "test": summ(ps) | {"per_session": [round(x, 4) for x in ps]}})
        bs = net["built_seed"]
        b = next(r for r in runs if r["seed"] == bs)["test"]["per_session"]
        sc = np.sort(M.twin_scores(C.model_of(net, bs), X), axis=1)
        rec["networks"][net["id"]] = {
            **{k: net[k] for k in ("format", "shape", "act_bits", "built_seed")}, "runs": runs,
            "tie_share_test_built_seed": round(float((sc[:, -1] == sc[:, -2]).mean()), 4),
            "test_mean_over_seeds": round(float(np.mean([r["test"]["mean"] for r in runs])), 4),
            "paired_vs": {k: paired(b, v) for k, v in ref.items()}}
        print(net["id"], [r["test"]["mean"] for r in runs], rec["networks"][net["id"]]["paired_vs"]["trivial_rule_87"], flush=True)
    (C.RES / "accuracy.json").write_text(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
