"""Design rounds on the train and validation splits only (the test split is never loaded here).

    python3 -m designs.b89_lutnet_gen.lutgen.explore <round> [--workers 3]

Each round is a list of named configurations in ROUNDS; every one is trained with seeds 0, 1 and 2. Writes
results/b89/rounds/<round>.json (validation and training accuracy per seed, epoch kept, table size) and the models
to build/b89/models/<round>/<name>_seed<s>.json.
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from . import data as Dm
from . import model as M

OUT = Dm.ROOT / "results" / "b89" / "rounds"
MODELS = Dm.ROOT / "build" / "b89" / "models"
SEEDS = (0, 1, 2)
T = dict(learn_temperature=True, freeze_bn=4)
B87 = dict(in_bits=[2] * 7, layers=[[16, 3, 2], [8, 3, 2]], out_fan_in=4, out_bits=4)

ROUNDS = {
    # round 1: the 87 structure with the training fixed (BatchNorm before each quantiser, cosine decay, best epoch)
    "r1": {
        "b87_shape_bn": dict(B87),
        "b87_shape_no_bn": dict(B87, batchnorm=False),
        "b87_shape_bn_3b_hidden": dict(B87, layers=[[16, 2, 3], [8, 2, 3]], out_fan_in=3),
        "one_hidden_bn": dict(in_bits=[2] * 7, layers=[[16, 3, 2]], out_fan_in=4, out_bits=4),
    },
    # round 2: additive score layer (class score = sum of several small tables), with and without a hidden layer,
    # and the input codes cut where a small tree ensemble cuts (thresholds="tree")
    "r2": {
        "add_noh_2b": dict(in_bits=[2] * 7, layers=[], output="additive", per_class=8, out_fan_in=3, out_bits=4),
        "add_noh_3b": dict(in_bits=[3] * 7, layers=[], output="additive", per_class=8, out_fan_in=3, out_bits=4),
        "add_noh_3b_tree": dict(in_bits=[3] * 7, thresholds="tree", layers=[], output="additive", per_class=8,
                                out_fan_in=3, out_bits=4),
        "add_h16_2b": dict(in_bits=[2] * 7, layers=[[16, 3, 2]], output="additive", per_class=4, out_fan_in=3,
                           out_bits=4),
        "add_h16_3b_tree": dict(in_bits=[3] * 7, thresholds="tree", layers=[[16, 2, 3]], output="additive",
                                per_class=4, out_fan_in=2, out_bits=4),
    },
    # round 3: a learned scale between the integer scores and the loss's logits (learn_temperature), and the BatchNorm
    # statistics frozen for the last 4 epochs, on the shapes of rounds 1 and 2
    "r3": {
        "t_b87_shape": dict(B87, **T),
        "t_one_hidden": dict(in_bits=[2] * 7, layers=[[16, 3, 2]], out_fan_in=4, out_bits=4, **T),
        "t_add_h16_2b": dict(in_bits=[2] * 7, layers=[[16, 3, 2]], output="additive", per_class=4, out_fan_in=3,
                             out_bits=4, **T),
        "t_add_noh_2b": dict(in_bits=[2] * 7, layers=[], output="additive", per_class=8, out_fan_in=3, out_bits=4, **T),
        "t_add_noh_2b_pc4": dict(in_bits=[2] * 7, layers=[], output="additive", per_class=4, out_fan_in=3, out_bits=4,
                                 **T),
        "t_add_noh_3b_tree": dict(in_bits=[3] * 7, thresholds="tree", layers=[], output="additive", per_class=8,
                                  out_fan_in=3, out_bits=4, **T),
        "t_add_noh_3b_tree_k2": dict(in_bits=[3] * 7, thresholds="tree", layers=[], output="additive", per_class=8,
                                     out_fan_in=2, out_bits=4, **T),
    },
    # not a design round: the cost curve for the write-up (LUTs against fan-in), lg_add's configuration at fan-in 1-4
    "fanin": {f"fanin{k}": dict(in_bits=[3] * 7, thresholds="tree", layers=[], output="additive", per_class=8,
                                out_fan_in=k, out_bits=4, **T) for k in (1, 2, 3, 4)},
}


def _job(args):
    rnd, name, kw, seed = args
    d = Dm.load(("train", "val"))
    (Xtr, ytr, _), (Xv, yv, _) = d["train"], d["val"]
    cfg = M.Config(**dict(kw, seed=seed))
    t0 = time.time()
    m = M.train(cfg, Xtr, ytr, Xv, yv, log=lambda s: None)
    (MODELS / rnd).mkdir(parents=True, exist_ok=True)
    M.save(m, MODELS / rnd / f"{name}_seed{seed}.json")
    tb = M.table_bits(m)
    return {"name": name, "seed": seed, "val": m["val_accuracy"], "train": m["train_accuracy"],
            "epoch_kept": m["epoch_kept"], "val_by_epoch": m["val_by_epoch"], "table_bits_total": tb["table_bits_total"],
            "max_address_bits": max(max(a) for a in tb["address_bits"]), "seconds": round(time.time() - t0, 1)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("round")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--seeds", nargs="*", type=int, default=list(SEEDS))
    a = ap.parse_args(argv)
    cfgs = {k: v for k, v in ROUNDS[a.round].items() if not a.only or k in a.only}
    jobs = [(a.round, n, kw, s) for n, kw in cfgs.items() for s in a.seeds]
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{a.round}.json"
    rec = json.loads(f.read_text()) if f.exists() else {"round": a.round, "splits_used": ["train", "val"], "configs": {}}
    with ProcessPoolExecutor(a.workers) as ex:
        for r in ex.map(_job, jobs):
            print(r["name"], r["seed"], r["train"], r["val"], r["epoch_kept"], flush=True)
            c = rec["configs"].setdefault(r["name"], {"config": M.Config(**cfgs[r["name"]]).to_dict(), "runs": []})
            c["runs"] = [x for x in c["runs"] if x["seed"] != r["seed"]] + [r]
            f.write_text(json.dumps(rec, indent=1))
    for n, c in rec["configs"].items():
        v = [x["val"] for x in c["runs"]]
        c["val_mean"] = round(float(np.mean(v)), 4)
        c["val_min"] = round(float(np.min(v)), 4)
    f.write_text(json.dumps(rec, indent=1))
    for n, c in rec["configs"].items():
        print(f"{n:28s} val mean {c['val_mean']}  min {c['val_min']}  table bits {c['runs'][0]['table_bits_total']}")


if __name__ == "__main__":
    main()
