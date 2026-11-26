"""Pytest entry: runs the cocotb bench on the register core for three seeds."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DESIGN_DIR = Path(__file__).resolve().parents[1]
TOPLEVEL = "fir32_core"  # the register core: clk, rst, h_* port, led, sfp_tx_disable
PARAMS = {}  # FIFO_DEPTH etc. keep the spec values; the bench is fast enough


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_fir_bench(seed):
    from flow import cocotb_run

    sources = sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    cocotb_run.run(
        "p4_fir_dsp",
        TOPLEVEL,
        sources,
        "bench_p4_fir_dsp",
        DESIGN_DIR / "tests",
        parameters=PARAMS,
        seed=seed,
    )
