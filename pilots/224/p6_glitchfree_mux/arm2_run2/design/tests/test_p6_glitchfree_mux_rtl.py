import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flow import cocotb_run  # noqa: E402

DESIGN = Path(__file__).resolve().parents[1]


def test_p6_glitchfree_mux_rtl():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p6_glitchfree_mux",
            "p6_clkmux_core",
            sources,
            ["p6_bench"],
            DESIGN / "tests",
            parameters={"GATE_LEN_DEFAULT": 300},
            seed=seed,
        )
