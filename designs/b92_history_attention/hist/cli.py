"""Generate the RTL of the built networks of stage 2 (results/b92/stage2_frozen.json).

    python -m designs.b92_history_attention.hist.cli rtl [--check]     # -> designs/b92_history_attention/rtl/gen/
"""
from __future__ import annotations

import argparse
import json
import sys

from designs.b91_lowbit.lowbit import rtl as R91
from . import rtl as R
from . import stage2 as S2
from . import stream as S

ROOT = S2.ROOT
GEN = ROOT / "designs" / "b92_history_attention" / "rtl" / "gen"
BUILT = ["ref_current", "a1_decay", "a4_lut", "a2_win8", "a2_win16"]       # attention is not built: it lost at the stage 2 test
ATTN = ["a3_top1", "a3_relu"]                                              # RTL generated and simulated, never built in Vivado


def frozen():
    return json.loads((S2.RES / "stage2_frozen.json").read_text())


def rec_of(arm):
    return json.loads(S2.mpath(arm, frozen()["built_seed"][arm]).read_text())


def files(arm: str) -> dict[str, str]:
    r = rec_of(arm)
    src = f"results/b92/models/{arm}_seed{r['seed']}.json"
    name = f"b92_{arm}"
    if arm == "ref_current":                      # the head alone on the 87 port (no history), the cost baseline
        return {name: R91.emit(r["head"], name, S.FBITS_CUR, pipe="comb", source=src)}
    return R.emit_arm(arm, r, name, source=src)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["rtl"])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    bad = 0
    GEN.mkdir(parents=True, exist_ok=True)
    for arm in BUILT + ATTN:
        for nm, txt in files(arm).items():
            f = GEN / f"{nm}.sv"
            if a.check:
                if not f.exists() or f.read_text() != txt:
                    print("out of date:", f)
                    bad = 1
            else:
                f.write_text(txt)
                print("wrote", f.relative_to(ROOT))
    return bad


if __name__ == "__main__":
    sys.exit(main())
