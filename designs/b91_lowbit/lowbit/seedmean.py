"""Post-hoc analysis added after the review of the pre-registered scoring (not part of docs/preregistration.md, and
labelled so in every table that uses it): the same paired comparison, but on the per-session accuracy averaged over the
three training seeds, so the training-seed spread is part of the comparison rather than hidden by the built-seed choice.
The references are the same per-session values as accuracy.json (the 87 and 89 references are single built models, so
they carry no seed average).

    python -m designs.b91_lowbit.lowbit.seedmean      # reads results/b91/accuracy.json -> results/b91/accuracy_seedmean.json
"""
from __future__ import annotations

import json

import numpy as np

from designs.b89_lutnet_gen.lutgen.evaluate import paired, summ
from . import cli as C


def main():
    acc = json.loads((C.RES / "accuracy.json").read_text())
    out = {"schema": "b91-accuracy-seedmean/1", "note": "post-hoc; per-session mean over the 3 training seeds; 95% t-interval over 10 sessions", "networks": {}}
    for nid, a in acc["networks"].items():
        ps = np.mean([r["test"]["per_session"] for r in a["runs"]], axis=0)
        out["networks"][nid] = {"seed_mean_test": summ(ps),
                                "paired_vs": {k: paired(ps, v["per_session"]) for k, v in acc["references"].items()}}
    (C.RES / "accuracy_seedmean.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
