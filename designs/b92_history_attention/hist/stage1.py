"""Stage 1 (the gate): do lagged history columns help the brief 87 boosted trees? CPU only.

    python -m designs.b92_history_attention.hist.stage1 val     # train every candidate on train, score validation, select
                                                                 #   -> results/b92/stage1_val.json   (no test data read)
    python -m designs.b92_history_attention.hist.stage1 test    # after the selection is committed: score test once
                                                                 #   -> results/b92/stage1_test.json

Candidates per generator: (a) current features; (b) lagfeat and lagprim with N in {4, 8, 16}; three training seeds each.
The gate candidate is the (family, N) with the best mean validation accuracy over the seeds (ties to the smaller N).
The gate: gate candidate minus (a), per test session averaged over the seeds, 95% t-interval over the 10 sessions, on the
self-exciting generator; it passes if the interval is above zero. Sensitivity (not a gate): histogram boosting, 100 rounds,
depth 4, for (a) and the gate candidate.
"""
from __future__ import annotations

import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from designs.b87_ml_trading.model import arms as A87
from . import prims as P

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / "results" / "b92"
BUILD = ROOT / "build" / "b92"
GENS = ("b87", "hawkes")
SEEDS = (0, 1, 2)
CANDS = [("none", 0)] + [(f, n) for f in ("lagfeat", "lagprim") for n in (4, 8, 16)]
T975_DF9 = 2.262


def cname(fam, n):
    return "current" if fam == "none" else f"{fam}{n}"


def _fit(job):
    gen, fam, n, seed, kind = job
    Xtr, ytr, _ = P.build(gen, "train", fam, n)
    if kind == "gbt":
        m = A87.gbt_fit(Xtr, ytr, seed)
    else:
        from sklearn.ensemble import HistGradientBoostingClassifier
        m = HistGradientBoostingClassifier(max_iter=100, max_depth=4, learning_rate=0.1, random_state=seed).fit(Xtr, ytr)
    Xv, yv, _ = P.build(gen, "val", fam, n)
    va = float((m.predict(Xv) == yv).mean())
    BUILD.mkdir(parents=True, exist_ok=True)
    with open(BUILD / f"{gen}_{cname(fam, n)}_{kind}_s{seed}.pkl", "wb") as f:
        pickle.dump(m, f)
    return gen, cname(fam, n), kind, seed, round(va, 4)


def per_session(pred, y, g):
    return np.array([float((pred[g == i] == y[g == i]).mean()) for i in range(int(g.max()) + 1)])


def summ(a):
    a = np.asarray(a, dtype=float)
    h = T975_DF9 * a.std(ddof=1) / np.sqrt(len(a))
    return {"mean": round(float(a.mean()), 4), "ci95": [round(float(a.mean() - h), 4), round(float(a.mean() + h), 4)]}


def select(val: dict, gen: str) -> tuple[str, int]:
    """Best mean validation accuracy over the seeds among the history candidates; ties to the smaller N."""
    best = None
    for fam, n in CANDS[1:]:
        v = float(np.mean(val[gen][cname(fam, n)]["gbt"]))
        if best is None or v > best[0] + 1e-12 or (abs(v - best[0]) <= 1e-12 and n < best[2]):
            best = (v, fam, n)
    return best[1], best[2]


def val_phase(workers=2):
    jobs = [(g, f, n, s, "gbt") for g in GENS for f, n in CANDS for s in SEEDS]
    val = {g: {cname(f, n): {"gbt": [None] * 3, "hist": [None] * 3} for f, n in CANDS} for g in GENS}
    with ProcessPoolExecutor(workers) as ex:
        for g, c, k, s, va in ex.map(_fit, jobs):
            val[g][c][k][s] = va
            print(g, c, k, s, va, flush=True)
    sel = {g: select(val, g) for g in GENS}
    jobs = [(g, f, n, s, "hist") for g in GENS for f, n in [("none", 0), sel[g]] for s in SEEDS]
    with ProcessPoolExecutor(workers) as ex:
        for g, c, k, s, va in ex.map(_fit, jobs):
            val[g][c][k][s] = va
            print(g, c, k, s, va, flush=True)
    rec = {"schema": "b92-stage1-val/1", "validation_accuracy": val,
           "gate_candidate": {g: {"family": sel[g][0], "n": sel[g][1], "name": cname(*sel[g])} for g in GENS}}
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "stage1_val.json").write_text(json.dumps(rec, indent=1))


def test_phase():
    v = json.loads((RES / "stage1_val.json").read_text())
    rec = {"schema": "b92-stage1-test/1", "interval": "95% t-interval over the 10 test sessions", "generators": {}}
    for gen in GENS:
        gc = v["gate_candidate"][gen]
        names = {cname(f, n): (f, n) for f, n in CANDS}
        out = {}
        data = {}
        for nm, (f, n) in names.items():
            Xte, yte, gte = P.build(gen, "test", f, n)
            data[nm] = (Xte, yte, gte)
        ps = {}
        for nm in names:
            Xte, yte, gte = data[nm]
            ps[nm] = {}
            for kind in ("gbt", "hist"):
                if kind == "hist" and nm not in ("current", gc["name"]):
                    continue
                arr = []
                for s in SEEDS:
                    m = pickle.load(open(BUILD / f"{gen}_{nm}_{kind}_s{s}.pkl", "rb"))
                    arr.append(per_session(m.predict(Xte), yte, gte))
                ps[nm][kind] = np.mean(arr, axis=0)                       # mean over seeds, per session
                out.setdefault(nm, {})[kind] = summ(ps[nm][kind]) | {"per_session": [round(float(x), 4) for x in ps[nm][kind]],
                                                                    "per_seed_mean": [round(float(x.mean()), 4) for x in arr]}
        cmp = {}
        for nm in names:
            if nm == "current":
                continue
            d = ps[nm]["gbt"] - ps["current"]["gbt"]
            cmp[nm] = summ(d)
        gd = ps[gc["name"]]["gbt"] - ps["current"]["gbt"]
        sd = ps[gc["name"]]["hist"] - ps["current"]["hist"]
        rec["generators"][gen] = {"gate_candidate": gc["name"], "arms": out, "paired_vs_current_gbt_all_candidates": cmp,
                                  "gate_difference": summ(gd), "gate_passes": bool(summ(gd)["ci95"][0] > 0),
                                  "sensitivity_hist_boosting_difference": summ(sd)}
        print(gen, gc["name"], summ(gd), summ(sd), flush=True)
    rec["gate"] = {"generator": "hawkes", "passes": rec["generators"]["hawkes"]["gate_passes"]}
    (RES / "stage1_test.json").write_text(json.dumps(rec, indent=1))


if __name__ == "__main__":
    {"val": val_phase, "test": test_phase}[sys.argv[1]]()
