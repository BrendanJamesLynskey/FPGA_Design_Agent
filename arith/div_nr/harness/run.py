#!/usr/bin/env python3
"""Rerun the div_nr verification against YOUR instance (brief 139c). See README.md in this folder.

    python3 arith/div_nr/harness/run.py --dut my_module --rtl my.sv ... --param W=24 --param A=9 --param IT=2 [--variant <id>] [--latency N]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from arith.common import harness_run                      # noqa: E402
from arith.div_nr import model as M                         # noqa: E402

P: dict = {}
W = 0


def plan(p, variant, count):
    w, ab, it = p["W"], p["A"], p["IT"]
    vid = {v: k_ for k_, v in M.VARIANTS.items()}.get(variant, 0)
    vin, vexp = M.stream(w, ab, it, vid, count if count else (None if w <= 8 else 4000))
    return vin, vexp, 2 * w, w, M.latency(vid, it)


def decode(vin):
    w = P["W"]
    msk = (1 << w) - 1
    return [{"a": v >> w, "b": v & msk, "w": w, "i": ((v & msk) >> (w - 4)) & 7} for v in vin]


if __name__ == "__main__":
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--param":
            k, v = argv[i + 1].split("=")
            P[k] = int(v)
    W = P.get("W", 0)
    sys.exit(harness_run.main(Path(__file__).resolve().parents[1], plan, decode))
