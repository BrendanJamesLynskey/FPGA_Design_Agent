#!/usr/bin/env python3
"""Rerun the sqrt_r4 verification against YOUR instance (brief 139c). See README.md in this folder.

    python3 arith/sqrt_r4/harness/run.py --dut my_module --rtl my.sv ... --param W=24 [--param PIPE=2] [--variant <id>] [--latency N]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from arith.common import harness_run                      # noqa: E402
from arith.sqrt_r4 import model as M                         # noqa: E402

P: dict = {}
W = 0


def plan(p, variant, count):
    w = p["W"]
    pipe = p.get("PIPE", 1)
    vid = {v: k for k, v in M.VARIANTS.items()}.get(variant, 1)
    vin, vexp = M.stream(w, count if count else (None if w <= 12 else 3000))
    return vin, vexp, w, 2 * M.rw(w) + 1, M.latency(vid, w, pipe)


def decode(vin):
    import math
    return [{"x": v, "r": math.isqrt(v), "m": (1 << P["W"]) - 1} for v in vin]


if __name__ == "__main__":
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--param":
            k, v = argv[i + 1].split("=")
            P[k] = int(v)
    W = P.get("W", 0)
    sys.exit(harness_run.main(Path(__file__).resolve().parents[1], plan, decode))
