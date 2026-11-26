"""Pytest entry: runs the cocotb bench on the register core for 3 seeds."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flow import cocotb_run  # noqa: E402

DESIGN_DIR = Path(__file__).resolve().parents[1]
TOPLEVEL = "p2_mem_test_core"  # register core: clk, rst, h_* port, led, sfp_tx_disable


def test_p2_bram_rom_rtl():
    sources = sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p2_bram_rom",
            TOPLEVEL,
            sources,
            ["test_p2_bram_rom_bench"],
            DESIGN_DIR / "tests",
            parameters={},
            seed=seed,
        )
