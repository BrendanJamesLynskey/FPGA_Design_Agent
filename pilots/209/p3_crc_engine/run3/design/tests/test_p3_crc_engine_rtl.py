import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flow import cocotb_run  # noqa: E402


def test_p3_crc_engine_rtl():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p3_crc_engine",
            "crc32_core",
            sources,
            "crc_bench",
            DESIGN / "tests",
            parameters={},
            seed=seed,
        )
