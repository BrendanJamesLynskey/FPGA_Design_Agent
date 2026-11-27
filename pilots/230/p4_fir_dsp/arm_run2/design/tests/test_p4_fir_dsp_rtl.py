import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
for p in [DESIGN, *DESIGN.parents]:
    if (p / "flow").is_dir():
        sys.path.insert(0, str(p))
        break
sys.path.insert(0, str(DESIGN))

from flow import cocotb_run  # noqa: E402


def test_p4_fir_dsp_rtl():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p4_fir_dsp",
            "fir32_core",
            sources,
            ["fir_bench"],
            DESIGN / "tests",
            parameters={},
            seed=seed,
        )
