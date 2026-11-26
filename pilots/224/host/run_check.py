#!/usr/bin/env python3
"""Run one pilot's hardware check (brief 209). Writes <out>/<design>.json and prints PASS or FAIL per criterion.

    python3 pilots/209/host/run_check.py <p1_clkmeter|...|p6_glitchfree_mux> --serial <cable serial> --expect-build <hex> --out <dir>

The program step and the stamp comparison are in pilots/209/run_pilot_board.sh; this script only talks to a design that is already loaded.
Exit status 0 only when every criterion passes; 3 for an inconclusive run (setup fault).
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bus import Clock, VivadoBus  # noqa: E402
from report import Inconclusive, Report  # noqa: E402

IDS = {"p1_clkmeter": 0x20910001, "p2_bram_rom": 0x20920001, "p3_crc_engine": 0x20930001, "p4_fir_dsp": 0x20940001,
       "p5_async_fifo": 0x20950001, "p6_glitchfree_mux": 0x20960001}


def check(design: str, bus, clk, expect_build: int | None, out: Path, **kw) -> Report:
    mod = importlib.import_module(f"check_{design}")
    rep = Report(design, IDS[design], expect_build)
    print(f"=== {design} host check ===", flush=True)
    try:
        mod.run(bus, rep, clk, **kw)
    except Inconclusive as e:
        print(f"INCONCLUSIVE: {e}", flush=True)
    except Exception as e:                    # a bus fault or a timeout: a setup or design fault, recorded, never a pass
        rep.aborted = f"{type(e).__name__}: {e}"
        print(f"INCONCLUSIVE: {rep.aborted}", flush=True)
    print(f"RESULT {design}: {rep.verdict()}", flush=True)
    rep.write(out)
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("design", choices=sorted(IDS))
    ap.add_argument("--serial", required=True)
    ap.add_argument("--expect-build", required=True, help="hex USR_ACCESS word of the build record")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    bus = VivadoBus(a.serial)
    try:
        rep = check(a.design, bus, Clock(), int(a.expect_build, 16), a.out)
    finally:
        bus.close()
    return 0 if rep.all_pass else (3 if rep.aborted else 1)


if __name__ == "__main__":
    sys.exit(main())
