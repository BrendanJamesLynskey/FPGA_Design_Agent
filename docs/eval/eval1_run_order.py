"""Fixed run order for the eval-1 held-out evaluation (pre-registered 2026-11-09).

Each of the 19 held-out tasks appears three times; the list is shuffled once with seed 20261109 and
run numbers are given in order of appearance. Usage: python3 docs/eval/eval1_run_order.py
"""
import random
import yaml

SPLITS = ["benchmark/split.yaml", "benchmark/course/split.yaml", "benchmark/course/split_c9_c12.yaml"]


def order(seed=20261109, runs=3):
    ids = []
    for f in SPLITS:
        d = yaml.safe_load(open(f))
        for tier in sorted(d["tiers"]):
            ids += d["tiers"][tier]["held_out"]
    slots = sorted(ids) * runs
    random.Random(seed).shuffle(slots)
    seen = {}
    out = []
    for t in slots:
        seen[t] = seen.get(t, 0) + 1
        out.append((t, seen[t]))
    return out


if __name__ == "__main__":
    for i, (t, r) in enumerate(order(), 1):
        print(f"{i:2d}. {t} run {r}")
