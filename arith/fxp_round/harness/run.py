#!/usr/bin/env python3
"""Rerun the fxp_round verification against YOUR instance (brief 139b). See README.md in this folder.

    python3 arith/fxp_round/harness/run.py --dut my_module --rtl my.sv ... --param W=24 [--param PIPE=2] [--variant <id>] [--latency N]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from arith.common import harness_run                      # noqa: E402
from arith.fxp_round import model as M                         # noqa: E402

P: dict = {}
W = 0


def plan(p, variant, count):
    w, s, wo, mode, sat = (p[k] for k in ("W_IN", "S", "W_OUT", "MODE", "SAT"))
    vid = {v: k for k, v in M.VARIANTS.items()}.get(variant, 0)
    vin, vexp = M.stream(w, s, wo, mode, sat, count if count else (None if w <= 10 else 3000))
    return vin, vexp, w, wo, M.latency(vid)


def decode(vin):
    s, w = P["S"], P["W_IN"]
    rows = []
    for v in vin:
        x = M.to_signed(v, w)
        rem = x & ((1 << s) - 1) if s else 0
        rows.append({"x": x, "tie": bool(s) and rem == (1 << (s - 1)), "neg": x < 0, "min": x == -(1 << (w - 1)), "max": x == (1 << (w - 1)) - 1, "s": s})
    return rows


if __name__ == "__main__":
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--param":
            k, v = argv[i + 1].split("=")
            P[k] = int(v)
    W = P.get("W_IN", 0)
    sys.exit(harness_run.main(Path(__file__).resolve().parents[1], plan, decode))
