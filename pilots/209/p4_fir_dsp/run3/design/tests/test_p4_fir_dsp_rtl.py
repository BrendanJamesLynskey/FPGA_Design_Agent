from pathlib import Path

import flow.cocotb_run

DESIGN = Path(__file__).resolve().parents[1]
TOP = "fir32_core"
SEEDS = (1, 2, 3)


def _sources():
    return sorted((DESIGN / "rtl").glob("*.sv"))


def test_p4_fir_dsp_rtl():
    for seed in SEEDS:
        flow.cocotb_run.run("p4_fir_dsp", TOP, _sources(), "fir_bench", DESIGN / "tests",
                            parameters={}, seed=seed)
