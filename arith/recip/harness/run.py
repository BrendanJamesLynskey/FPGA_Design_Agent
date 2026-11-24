#!/usr/bin/env python3
"""Rerun the recip verification against YOUR instance (brief 139c). See README.md in this folder.

    python3 arith/recip/harness/run.py --dut my_module --rtl my.sv ... --param W=24 --param A=9 [--variant <id>] [--latency N]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from arith.common import harness_run                      # noqa: E402
from arith.recip import model as M                         # noqa: E402

P: dict = {}
W = 0


def plan(p, variant, count):
    w, a = p["W"], p["A"]
    vid = {v: k_ for k_, v in M.VARIANTS.items()}.get(variant, 1)
    vin, vexp = M.stream(w, a, vid, count if count else (None if w <= 12 else 3000))
    return vin, vexp, w, w + 1, M.latency(vid)


def decode(vin):
    w, a = P["W"], P["A"]
    return [{"b": v, "w": w, "idx": (v >> (w - 1 - a)) & ((1 << a) - 1), "na": (1 << a) - 1} for v in vin]


if __name__ == "__main__":
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--param":
            k, v = argv[i + 1].split("=")
            P[k] = int(v)
    W = P.get("W", 0)
    sys.exit(harness_run.main(Path(__file__).resolve().parents[1], plan, decode))
