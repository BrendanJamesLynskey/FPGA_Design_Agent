"""Stage 2: the history arms on the self-exciting generator, one common head.

    python -m designs.b92_history_attention.hist.stage2 fit      # train on train, score validation only -> results/b92/models/, rounds/
    python -m designs.b92_history_attention.hist.stage2 freeze   # built seeds and the rate-set choice -> results/b92/stage2_frozen.json
    python -m designs.b92_history_attention.hist.stage2 test     # after the freeze is committed: score test once -> results/b92/stage2_accuracy.json

Arms (docs/design.md section 4; docs/preregistration_stage2.md): ref_current (the head on the 7 current features), a1_decay,
a2_win16, a2_win8, a3_top1, a3_relu, a4_lut (89 lg_small network on the arm 1 columns), ref_lut (lg_small on current), ref_mlp (87 MLP).
Head: brief 91 `log4`, hidden 16 then 8, 4-bit codes, 30 epochs. Three seeds each; the built seed is the best on validation.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from designs.b87_ml_trading.model import arms as A87
from designs.b89_lutnet_gen.lutgen import model as M89
from designs.b91_lowbit.lowbit import model as M91
from . import attn as AT
from . import frontends as FE
from . import tokens as TK

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / "results" / "b92"
MODELS = RES / "models"
SEEDS = (0, 1, 2)
EPOCHS = 30
T975_DF9 = 2.262
HEAD = dict(fmt="log4", hidden=[16, 8], act_bits=4, epochs=EPOCHS)
LG_SMALL = {"in_bits": [3] * 7, "thresholds": "tree", "layers": [], "out_fan_in": 2, "out_bits": 4, "output": "additive",
            "per_class": 8, "wiring": "random", "hidden": 16, "depth": 2, "batchnorm": True, "freeze_bn": 4,
            "learn_temperature": True, "epochs": 20, "lr": 0.003, "batch": 1024, "n_classes": 3}
ARMS = ["ref_current", "a1_decay", "a2_win16", "a2_win8", "a3_top1", "a3_relu", "a4_lut", "ref_lut", "ref_mlp"]
FBITS_CUR = [8, 8, 4, 3, 5, 8, 2]


def splits(names=("train", "val")):
    return {n: TK.Split("hawkes", n) for n in names}


def fronts_columns(arm: str, front: dict, sp) -> np.ndarray:
    """Extra columns of an arm for one Split (current features are not included)."""
    if arm == "a1_decay":
        return sp.apply(lambda s: FE.decay_cols(s, front))
    if arm in ("a2_win16", "a2_win8"):
        n = 16 if arm == "a2_win16" else 8
        return sp.apply(lambda s: FE.window_cols(s, front, n))
    if arm in ("a3_top1", "a3_relu"):
        C = M89.encode(front["cth"], sp.X)
        U = sp.apply(lambda s: AT.window_raw(s["T"]).reshape(len(s["T"]), -1)).reshape(len(sp.X), AT.N_WIN, 4)
        return AT.twin(front, C, U)
    return np.zeros((len(sp.X), 0), dtype=np.int64)


def front_bits(arm: str, front: dict) -> list[int]:
    if arm == "a1_decay":
        return [8] * (4 * len(front["rates"]))
    if arm in ("a2_win16", "a2_win8"):
        return front["bits"] * (16 if arm == "a2_win16" else 8)
    if arm in ("a3_top1", "a3_relu"):
        return [4] * AT.MV
    return []


def all_columns(arm, front, sp):
    return np.concatenate([sp.X, fronts_columns(arm, front, sp)], axis=1)


def mpath(arm, seed, tag=""):
    return MODELS / f"{arm}{tag}_seed{seed}.json"


def _job(job):
    arm, seed, opt = job            # opt: the rate-set name for a1, else None
    sp = splits()
    tr, va = sp["train"], sp["val"]
    front = {}
    tag = ""
    if arm == "a1_decay":
        front = FE.fit_decay(tr, FE.RATE_SETS[opt])
        tag = "_" + opt
    elif arm in ("a2_win16", "a2_win8"):
        front = FE.fit_token_codes(tr)
    elif arm in ("a3_top1", "a3_relu"):
        cth = AT.fit_cur_codes(tr.X, tr.y)
        mk = lambda s: (M89.encode(cth, s.X), s.apply(lambda ss: AT.window_raw(ss["T"]).reshape(len(ss["T"]), -1)).reshape(len(s.X), AT.N_WIN, 4))  # noqa: E731
        C, U = mk(tr)
        Cv, Uv = mk(va)
        front = AT.train(arm.split("_")[1], seed, C, U, tr.y, Cv, Uv, va.y, log=lambda s: None)
        front["cth"] = cth
    Xtr, Xv = all_columns(arm, front, tr), all_columns(arm, front, va)
    rec = {"arm": arm, "seed": seed, "front": front, "front_bits": front_bits(arm, front)}
    if arm in ("ref_current", "a1_decay", "a2_win16", "a2_win8", "a3_top1", "a3_relu"):
        m = M91.train(M91.Config(**HEAD, seed=seed), Xtr, tr.y, Xv, va.y, log=lambda s: None)
        rec["head"] = m
        rec["val_accuracy"] = m["val_accuracy"]
    elif arm in ("a4_lut", "ref_lut"):
        cfg = dict(LG_SMALL, in_bits=[3] * Xtr.shape[1], seed=seed)
        m = M89.train(M89.Config(**cfg), Xtr, tr.y, Xv, va.y, log=lambda s: None)
        rec["head"] = m
        rec["val_accuracy"] = m["val_accuracy"]
    elif arm == "ref_mlp":
        r = A87.mlp_fit(Xtr, tr.y, Xv, va.y, seed)
        rec["head"] = r["int"]
        rec["val_accuracy"] = round(float((A87.mlp_predict_int(r["int"], Xv) == va.y).mean()), 4)
    MODELS.mkdir(parents=True, exist_ok=True)
    mpath(arm, seed, tag).write_text(json.dumps(rec))
    return arm + tag, seed, rec["val_accuracy"]


def predict(rec: dict, sp) -> np.ndarray:
    arm = rec["arm"]
    X = all_columns(arm, rec["front"], sp)
    if arm == "ref_mlp":
        return A87.mlp_predict_int(rec["head"], X)
    if arm in ("a4_lut", "ref_lut"):
        return M89.twin_predict(rec["head"], X)
    return M91.twin_predict(rec["head"], X)


def fit(workers=2):
    jobs = [("a1_decay", s, o) for o in FE.RATE_SETS for s in SEEDS]
    jobs += [(a, s, None) for a in ARMS if a not in ("a1_decay", "a4_lut") for s in SEEDS]
    val = {}
    with ProcessPoolExecutor(workers) as ex:
        for name, s, va in ex.map(_job, jobs):
            print(name, s, va, flush=True)
            val.setdefault(name, {})[s] = va
    # arm 1's rate set, chosen on mean validation accuracy (ties to the slower-decaying set listed first)
    rs = max(FE.RATE_SETS, key=lambda o: (np.mean([val[f"a1_decay_{o}"][s] for s in SEEDS]), -list(FE.RATE_SETS).index(o)))
    print("rate set", rs, flush=True)
    for s in SEEDS:                               # the chosen set becomes a1_decay itself; a4 uses its front end
        r = json.loads(mpath("a1_decay", s, "_" + rs).read_text())
        mpath("a1_decay", s).write_text(json.dumps(r))
        val.setdefault("a1_decay", {})[s] = r["val_accuracy"]
    a4 = []
    with ProcessPoolExecutor(workers) as ex:
        for name, s, va in ex.map(_job_a4, [(s, rs) for s in SEEDS]):
            print(name, s, va, flush=True)
            val.setdefault(name, {})[s] = va
    (RES / "rounds").mkdir(parents=True, exist_ok=True)
    (RES / "rounds" / "stage2_val.json").write_text(json.dumps({"rate_set": rs, "validation_accuracy": val}, indent=1))


def _job_a4(job):
    seed, rs = job
    base = json.loads(mpath("a1_decay", seed).read_text())
    sp = splits()
    tr, va = sp["train"], sp["val"]
    front = base["front"]
    Xtr, Xv = all_columns("a1_decay", front, tr), all_columns("a1_decay", front, va)
    cfg = dict(LG_SMALL, in_bits=[3] * Xtr.shape[1], seed=seed)
    m = M89.train(M89.Config(**cfg), Xtr, tr.y, Xv, va.y, log=lambda s: None)
    rec = {"arm": "a4_lut", "seed": seed, "front": front, "front_bits": base["front_bits"], "head": m,
           "val_accuracy": m["val_accuracy"], "decay_front_of_seed": seed}
    mpath("a4_lut", seed).write_text(json.dumps(rec))
    return "a4_lut", seed, rec["val_accuracy"]


def built_seed(arm: str) -> int:
    v = [(json.loads(mpath(arm, s).read_text())["val_accuracy"], -s) for s in SEEDS]
    return -max(v)[1]


def freeze():
    v = json.loads((RES / "rounds" / "stage2_val.json").read_text())
    rec = {"rate_set": v["rate_set"], "built_seed": {a: built_seed(a) for a in ARMS},
           "validation_accuracy": {a: v["validation_accuracy"][a] for a in ARMS}}
    (RES / "stage2_frozen.json").write_text(json.dumps(rec, indent=1))
    print(rec)


def per_session(pred, y, g):
    return np.array([float((pred[g == i] == y[g == i]).mean()) for i in range(int(g.max()) + 1)])


def summ(a):
    a = np.asarray(a, dtype=float)
    h = T975_DF9 * a.std(ddof=1) / np.sqrt(len(a))
    return {"mean": round(float(a.mean()), 4), "ci95": [round(float(a.mean() - h), 4), round(float(a.mean() + h), 4)]}


def paired(a, b):
    r = summ(np.asarray(a) - np.asarray(b))
    return {"difference_mean": r["mean"], "ci95": r["ci95"], "a_better": bool(r["ci95"][0] > 0), "b_better": bool(r["ci95"][1] < 0)}


def test():
    fr = json.loads((RES / "stage2_frozen.json").read_text())
    te = splits(("test",))["test"]
    s1 = json.loads((RES / "stage1_test.json").read_text())["generators"]["hawkes"]["arms"]
    from designs.b92_history_attention.hist import prims as P
    tr = splits(("train", "val"))
    rule = A87.imbalance_rule_fit(tr["val"].X, tr["val"].y)
    ref = {"trivial_rule": per_session(A87.imbalance_rule_predict(rule, te.X), te.y, te.g),
           "trees_87_current": np.array(s1["current"]["gbt"]["per_session"]),
           "trees_lagfeat16": np.array(s1["lagfeat16"]["gbt"]["per_session"])}
    rec = {"schema": "b92-stage2-accuracy/1", "interval": "95% t-interval over the 10 test sessions", "rate_set": fr["rate_set"],
           "references": {k: {"per_session": [round(float(x), 4) for x in v], **summ(v)} for k, v in ref.items()}, "arms": {}}
    ps_built = {}
    for arm in ARMS:
        runs = []
        for s in SEEDS:
            r = json.loads(mpath(arm, s).read_text())
            ps = per_session(predict(r, te), te.y, te.g)
            runs.append({"seed": s, "val": r["val_accuracy"], "test": summ(ps) | {"per_session": [round(float(x), 4) for x in ps]}})
        b = fr["built_seed"][arm]
        ps_built[arm] = np.array(next(x for x in runs if x["seed"] == b)["test"]["per_session"])
        rec["arms"][arm] = {"built_seed": b, "runs": runs, "test_mean_over_seeds": round(float(np.mean([x["test"]["mean"] for x in runs])), 4)}
    for arm in ARMS:
        a = ps_built[arm]
        rec["arms"][arm]["paired_vs"] = {k: paired(a, v) for k, v in {**ref, **{"ref_current": ps_built["ref_current"], "a1_decay": ps_built["a1_decay"]}}.items()}
    rec["attention_vs_decay"] = {"a3_top1": paired(ps_built["a3_top1"], ps_built["a1_decay"]),
                                 "a3_relu": paired(ps_built["a3_relu"], ps_built["a1_decay"])}
    (RES / "stage2_accuracy.json").write_text(json.dumps(rec, indent=1))
    for arm in ARMS:
        print(arm, rec["arms"][arm]["test_mean_over_seeds"], rec["arms"][arm]["paired_vs"]["trivial_rule"]["difference_mean"], flush=True)
    print(rec["attention_vs_decay"])


if __name__ == "__main__":
    {"fit": fit, "freeze": freeze, "test": test}[sys.argv[1]]()
