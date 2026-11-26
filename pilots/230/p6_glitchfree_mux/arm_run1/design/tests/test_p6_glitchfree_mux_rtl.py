import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flow import cocotb_run

DESIGN = Path(__file__).resolve().parents[1]
PARAMS = {"GATE_LEN_DEFAULT_CYCLES": 150}


def test_p6_glitchfree_mux_rtl():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p6_glitchfree_mux",
            "p6_clkmux_core",
            sources,
            ["bench_p6_glitchfree_mux"],
            DESIGN / "tests",
            parameters=PARAMS,
            seed=seed,
        )
