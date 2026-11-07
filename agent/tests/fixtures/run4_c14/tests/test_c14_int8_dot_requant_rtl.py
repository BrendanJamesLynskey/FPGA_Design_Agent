"""Pytest entry: runs the cocotb bench (tests/c14_bench.py) against the RTL for several seeds."""
import sys
from pathlib import Path

DESIGN_DIR = Path(__file__).resolve().parents[1]
for _p in Path(__file__).resolve().parents:
    if (_p / "flow" / "cocotb_run.py").exists():
        sys.path.insert(0, str(_p))
        break
sys.path.insert(0, str(DESIGN_DIR))

from flow import cocotb_run  # noqa: E402

NAME = "c14_int8_dot_requant"
TOPLEVEL = "c14_int8_dot_requant_top"
# Same values as CPB / TIMEOUT / BUILD in tests/c14_bench.py (and the model).
PARAMS = {"CLKS_PER_BIT": 8, "TIMEOUT_CYCLES": 2000, "BUILD_STAMP": 0x1BADB002}


def _run(seed):
    sources = cocotb_run.SHELL_RTL + sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    res = cocotb_run.run(NAME, TOPLEVEL, sources, "c14_bench", Path(__file__).resolve().parent,
                         parameters=PARAMS, seed=seed)
    if isinstance(res, bool):
        assert res
    return res


def test_seed_1():
    _run(1)


def test_seed_2():
    _run(2)


def test_seed_3():
    _run(3)
