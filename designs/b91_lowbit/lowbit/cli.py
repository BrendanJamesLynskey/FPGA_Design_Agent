"""Brief 91 driver. Training uses the train split and scores validation only; the test split is read only by
evaluate.py, after docs/preregistration.md and results/b91/frozen.json are committed.

    python -m designs.b91_lowbit.lowbit.cli stage1      # formats x shapes x 3 seeds at the base activation width -> results/b91/rounds/stage1.json
    python -m designs.b91_lowbit.lowbit.cli select      # rule on validation -> results/b91/rounds/select.json (the two sweep families)
    python -m designs.b91_lowbit.lowbit.cli stage2      # activation-width sweep of the two families -> results/b91/rounds/stage2.json
    python -m designs.b91_lowbit.lowbit.cli freeze      # the networks that get built -> results/b91/frozen.json
    python -m designs.b91_lowbit.lowbit.cli rtl [--check]   # RTL of every frozen network -> rtl/gen/
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from designs.b89_lutnet_gen.lutgen import data as Dm
from . import formats as F
from . import model as M
from . import rtl as R
from . import sim as S

ROOT = Dm.ROOT
RES = ROOT / "results" / "b91"
GEN = ROOT / "designs" / "b91_lowbit" / "rtl" / "gen"
SEEDS = (0, 1, 2)
FORMATS = ["binary_t3", "binary_t7", "ternary", "int4", "mxfp4", "log4", "log4_nz", "log4p1"]
SHAPES = {"h16x8": [16, 8], "h8": [8]}
BASE_A = 4
SWEEP_A = (2, 8)
EPOCHS = 30


def mname(fmt, shape, a, seed=None):
    s = f"{fmt}_{shape}_a{a}"
    return s if seed is None else f"{s}_seed{seed}"


def path_of(fmt, shape, a, seed):
    return RES / "models" / f"{mname(fmt, shape, a, seed)}.json"


def _train(job):
    fmt, shape, a, seed = job
    d = Dm.load(("train", "val"))
    (Xtr, ytr, _), (Xv, yv, _) = d["train"], d["val"]
    cfg = M.Config(fmt=fmt, hidden=SHAPES[shape], act_bits=a, seed=seed, epochs=EPOCHS)
    m = M.train(cfg, Xtr, ytr, Xv, yv, log=lambda s: None)
    m["shape"] = shape
    (RES / "models").mkdir(parents=True, exist_ok=True)
    M.save(m, path_of(fmt, shape, a, seed))
    return fmt, shape, a, seed, m["val_accuracy"], m["epoch_kept"]


def run_jobs(jobs, workers=2):
    out = []
    with ProcessPoolExecutor(workers) as ex:
        for r in ex.map(_train, jobs):
            print(*r, flush=True)
            out.append(r)
    return out


def table(fmt, shape, a):
    v = [json.loads(path_of(fmt, shape, a, s).read_text())["val_accuracy"] for s in SEEDS]
    return {"val": v, "val_mean": round(float(np.mean(v)), 4), "built_seed": int(np.argmax(v))}   # argmax: ties to lower


def stage1():
    run_jobs([(f, sh, BASE_A, s) for f in FORMATS for sh in SHAPES for s in SEEDS])
    rec = {f: {sh: table(f, sh, BASE_A) for sh in SHAPES} for f in FORMATS}
    (RES / "rounds").mkdir(parents=True, exist_ok=True)
    (RES / "rounds" / "stage1.json").write_text(json.dumps(rec, indent=1))


def best_shape(rec_f):
    """The shape with the higher mean validation accuracy; ties to the smaller network."""
    order = sorted(SHAPES, key=lambda s: (-rec_f[s]["val_mean"], sum(SHAPES[s])))
    return order[0]


def select():
    s1 = json.loads((RES / "rounds" / "stage1.json").read_text())
    sel = {f: best_shape(s1[f]) for f in FORMATS}
    fam = {}
    for f in FORMATS:
        k = F.FAMILY[f]
        v = s1[f][sel[f]]["val_mean"]
        if k not in fam or v > fam[k][1]:
            fam[k] = (f, v)
    cand = {k: v for k, v in fam.items() if k != "binary"}      # binary has 1-bit activations: no width to sweep
    top = sorted(cand.items(), key=lambda kv: (-kv[1][1], kv[1][0]))[:2]
    rec = {"selected_shape": sel, "family_representative": {k: {"format": v[0], "val_mean": v[1]} for k, v in fam.items()},
           "sweep": [{"family": k, "format": v[0], "shape": sel[v[0]]} for k, v in top]}
    (RES / "rounds" / "select.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec["sweep"]))


def stage2():
    sel = json.loads((RES / "rounds" / "select.json").read_text())
    run_jobs([(x["format"], x["shape"], a, s) for x in sel["sweep"] for a in SWEEP_A for s in SEEDS])
    s1 = json.loads((RES / "rounds" / "stage1.json").read_text())
    rec = {}
    for x in sel["sweep"]:
        t = {a: table(x["format"], x["shape"], a) for a in SWEEP_A}
        t[BASE_A] = s1[x["format"]][x["shape"]]
        best = sorted(t, key=lambda a: (-t[a]["val_mean"], a))[0]
        rec[x["format"]] = {"shape": x["shape"], "by_act_bits": {str(a): t[a] for a in sorted(t)}, "selected_act_bits": best}
    (RES / "rounds" / "stage2.json").write_text(json.dumps(rec, indent=1))


def freeze():
    sel = json.loads((RES / "rounds" / "select.json").read_text())
    s2 = json.loads((RES / "rounds" / "stage2.json").read_text())
    nets = []
    for f in FORMATS:
        sh = sel["selected_shape"][f]
        for a in sorted([BASE_A] + (list(SWEEP_A) if f in s2 else [])):
            nets.append({"format": f, "shape": sh, "act_bits": a})
    rec = {"schema": "b91-frozen/1", "seeds": list(SEEDS), "base_act_bits": BASE_A, "epochs": EPOCHS,
           "rule": "docs/preregistration.md", "networks": []}
    for n in nets:
        t = table(n["format"], n["shape"], n["act_bits"])
        rec["networks"].append({"id": mname(n["format"], n["shape"], n["act_bits"]), **{k: n[k] for k in ("format", "shape", "act_bits")},
                                "built_seed": t["built_seed"], "val_mean": t["val_mean"],
                                "is_base": n["act_bits"] == BASE_A,
                                "is_selected_act": (n["format"] not in s2) or n["act_bits"] == s2[n["format"]]["selected_act_bits"],
                                "pipes": ["comb", "layer"] if n["act_bits"] == BASE_A else ["comb"]})
    (RES / "frozen.json").write_text(json.dumps(rec, indent=1))


def frozen():
    return json.loads((RES / "frozen.json").read_text())


def model_of(net: dict, seed=None):
    return M.load(path_of(net["format"], net["shape"], net["act_bits"], net["built_seed"] if seed is None else seed))


def module_name(net, pipe):
    return f"lb_{net['id']}_{pipe}"


def rtl(check: bool) -> int:
    bad = 0
    for net in frozen()["networks"]:
        m = model_of(net)
        for pipe in net["pipes"]:
            name = module_name(net, pipe)
            txt = R.emit(m, name, S.FBITS, pipe=pipe, source=f"results/b91/models/{mname(net['format'], net['shape'], net['act_bits'], net['built_seed'])}.json")
            f = GEN / f"{name}.sv"
            if check:
                if not f.exists() or f.read_text() != txt:
                    print("out of date:", f)
                    bad = 1
            else:
                GEN.mkdir(parents=True, exist_ok=True)
                f.write_text(txt)
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["stage1", "select", "stage2", "freeze", "rtl"])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.step == "rtl":
        return rtl(a.check)
    globals()[a.step]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
