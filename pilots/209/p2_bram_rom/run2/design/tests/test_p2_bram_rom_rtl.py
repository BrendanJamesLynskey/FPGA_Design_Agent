import sys
from pathlib import Path

import pytest

DESIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN))
sys.path.insert(0, str(DESIGN / "tests"))

from flow import cocotb_run  # noqa: E402

SEEDS = (1, 2, 3)


@pytest.mark.parametrize("seed", SEEDS)
def test_p2_bram_rom_rtl(seed):
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    cocotb_run.run(
        "p2_bram_rom",
        "p2_core",
        sources,
        ["bench_p2_bram_rom"],
        DESIGN / "tests",
        parameters={},
        seed=seed,
    )
