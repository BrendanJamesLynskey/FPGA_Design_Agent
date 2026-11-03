#!/usr/bin/env python3
"""The held-out draw (brief 06a): per tier, about a third of the tasks held out, by a seeded random draw.

    split.py draw --seed N --out benchmark/split.yaml ID...
    split.py show benchmark/split.yaml

The seed is fixed and written down before the draw; the draw is `random.Random(seed).sample(sorted(tier ids),
round(n/3))` per tier (T1, T2), so anyone can re-run it and get the same split. Held-out tasks are never used while
tuning the agent; development tasks are open for agent work.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import yaml


def draw(ids: list[str], seed: int) -> dict:
    tiers: dict[str, list[str]] = {}
    for i in sorted(ids):
        tiers.setdefault(i.split("_")[0].upper(), []).append(i)
    out = {"seed": seed, "method": "per tier: random.Random(seed).sample(sorted(ids), round(n / 3)); tiers in "
                                   "sorted order, one Random instance per tier",
           "python": sys.version.split()[0], "date": time.strftime("%Y-%m-%d"), "tiers": {}}
    for t in sorted(tiers):
        pool = tiers[t]
        held = sorted(random.Random(seed).sample(pool, round(len(pool) / 3)))
        out["tiers"][t] = {"n": len(pool), "held_out": held, "dev": [i for i in pool if i not in held]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw")
    d.add_argument("--seed", type=int, required=True)
    d.add_argument("--out", type=Path, required=True)
    d.add_argument("ids", nargs="+")
    s = sub.add_parser("show")
    s.add_argument("file", type=Path)
    a = ap.parse_args()
    if a.cmd == "draw":
        r = draw(a.ids, a.seed)
        a.out.write_text("# The held-out split of benchmark v1 (benchmark/tools/split.py); never edit by hand.\n"
                         + yaml.safe_dump(r, sort_keys=False))
    else:
        r = yaml.safe_load(a.file.read_text())
    for t, v in r["tiers"].items():
        print(f"{t}: {v['n']} tasks, held out {len(v['held_out'])}: {', '.join(v['held_out'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
