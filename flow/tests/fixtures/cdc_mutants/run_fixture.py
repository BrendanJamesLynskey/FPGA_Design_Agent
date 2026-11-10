#!/usr/bin/env python3
"""Run one CDC fixture's cocotb test under Icarus: run_fixture.py <fixture> [<injection seed>] (0 or none: plain).
Exit 0 = the test passed. Used by make_table.py and flow/tests/test_16_cdc_gate.py."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

NAMES = sorted(p.stem for p in (HERE / "rtl").glob("*.sv"))


def run(name: str, seed: int = 0, build_root: Path | None = None) -> None:
    """Raises AssertionError when the fixture's test fails."""
    from flow import cocotb_run
    os.environ["CDCFX_NAME"] = name
    if seed:
        os.environ["FDA_CDC_INJECT_SEED"] = str(seed)
    else:
        os.environ.pop("FDA_CDC_INJECT_SEED", None)
    cocotb_run.run(f"cdcfx_{name}_{seed}", name, [HERE / "rtl" / f"{name}.sv"], "cdcfx_tb", HERE / "tb", seed=1,
                   build_root=build_root or Path(tempfile.gettempdir()) / "cdcfx_build")


if __name__ == "__main__":
    try:
        run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    except AssertionError as e:
        print("FAIL", str(e)[-400:])
        sys.exit(1)
    print("PASS")
