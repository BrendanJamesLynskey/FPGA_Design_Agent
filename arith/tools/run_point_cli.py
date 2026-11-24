#!/usr/bin/env python3
"""Run one variant at one point in its own process (the mutation runner starts one of these per mutant and point).

    python -m arith.tools.run_point_cli FUNCTION VARIANT MODE 'PARAMS-JSON' [--rtl-dir DIR] [--build-root DIR] [--n N]

Exit 0: the bench passed. Exit 1: the bench failed (a mismatch against the model). Exit 3: the run did not build or did not start."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from arith.tools import arith_common as ac


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("function")
    ap.add_argument("variant")
    ap.add_argument("mode")
    ap.add_argument("params")
    ap.add_argument("--rtl-dir")
    ap.add_argument("--build-root")
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    try:
        ac.run_point(a.function, a.variant, json.loads(a.params), a.mode, Path(a.rtl_dir) if a.rtl_dir else None, seed=a.seed, n=a.n,
                     build_root=Path(a.build_root) if a.build_root else None)
    except AssertionError as e:
        print("FAILED:", str(e)[:400])
        return 1
    except BaseException as e:           # noqa: BLE001  a build error, a missing tool
        print("DID NOT RUN:", type(e).__name__, str(e)[:400])
        return 3
    print("passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
