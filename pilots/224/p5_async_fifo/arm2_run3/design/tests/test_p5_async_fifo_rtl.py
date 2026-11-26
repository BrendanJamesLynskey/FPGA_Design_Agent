import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flow import cocotb_run  # noqa: E402

DESIGN_DIR = Path(__file__).resolve().parents[1]
TOPLEVEL = "p5_async_fifo_core"


def test_p5_async_fifo_rtl():
    sources = sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p5_async_fifo",
            TOPLEVEL,
            sources,
            "bench_p5_async_fifo",
            DESIGN_DIR / "tests",
            parameters={},
            seed=seed,
        )
