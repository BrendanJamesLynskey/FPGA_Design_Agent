"""pytest entry: runs the cocotb bench on the register core for three seeds."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flow import cocotb_run  # noqa: E402

DESIGN_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_p4_fir_dsp_rtl(seed):
    sources = sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    cocotb_run.run(
        "p4_fir_dsp",
        "fir_core",
        sources,
        ["bench_fir"],
        DESIGN_DIR / "tests",
        seed=seed,
    )
