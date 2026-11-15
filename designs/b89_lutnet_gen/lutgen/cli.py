"""Train the frozen brief 89 networks (results/b89/frozen.json), keep the models, emit the RTL.

    python -m designs.b89_lutnet_gen.lutgen.cli train            # three seeds per arm -> results/b89/models/
    python -m designs.b89_lutnet_gen.lutgen.cli rtl [--check]    # RTL of each arm's built seed -> rtl/gen/

frozen.json: {"arms": {<arm>: {"config": {...Config fields}, "pipes": ["comb", "layer"]}}}. The built seed of an arm
is the one with the best validation accuracy (ties to the lower seed); the test split is not used here. Each
(arm, pipe) becomes module `<arm>_<pipe>` in rtl/gen/<arm>_<pipe>.sv.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor

from . import data as Dm
from . import model as M
from . import rtl as R
from . import sim as S

RES = Dm.ROOT / "results" / "b89"
GEN = Dm.ROOT / "designs" / "b89_lutnet_gen" / "rtl" / "gen"
SEEDS = (0, 1, 2)


def frozen():
    return json.loads((RES / "frozen.json").read_text())


def _train(args):
    arm, cfg, seed = args
    d = Dm.load(("train", "val"))
    (Xtr, ytr, _), (Xv, yv, _) = d["train"], d["val"]
    m = M.train(M.Config(**dict(cfg, seed=seed)), Xtr, ytr, Xv, yv, log=lambda s: None)
    (RES / "models").mkdir(parents=True, exist_ok=True)
    M.save(m, RES / "models" / f"{arm}_seed{seed}.json")
    return arm, seed, m["val_accuracy"]


def built_seed(arm: str) -> int:
    v = [(json.loads((RES / "models" / f"{arm}_seed{s}.json").read_text())["val_accuracy"], -s) for s in SEEDS]
    return -max(v)[1]


def model_of(arm: str, seed: int | None = None) -> dict:
    s = built_seed(arm) if seed is None else seed
    return json.loads((RES / "models" / f"{arm}_seed{s}.json").read_text())


def rtl(check: bool) -> int:
    bad = 0
    for arm, a in frozen()["arms"].items():
        s = built_seed(arm)
        m = model_of(arm, s)
        for pipe in a["pipes"]:
            name = f"{arm}_{pipe}"
            txt = R.emit(m, name, S.FBITS, pipe=pipe, source=f"results/b89/models/{arm}_seed{s}.json")
            f = GEN / f"{name}.sv"
            if check:
                if not f.exists() or f.read_text() != txt:
                    print(f"out of date: {f}")
                    bad = 1
            else:
                GEN.mkdir(parents=True, exist_ok=True)
                f.write_text(txt)
                print("wrote", f.relative_to(Dm.ROOT))
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["train", "rtl"])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args(argv)
    if a.step == "train":
        jobs = [(arm, x["config"], s) for arm, x in frozen()["arms"].items() for s in SEEDS]
        with ProcessPoolExecutor(a.workers) as ex:
            for r in ex.map(_train, jobs):
                print(*r, flush=True)
        return 0
    return rtl(a.check)


if __name__ == "__main__":
    sys.exit(main())
