import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_p4_fir_dsp_rtl():
    from flow import cocotb_run

    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p4_fir_dsp",
            "fir32_core",
            sources,
            "fir_bench",
            Path(__file__).resolve().parent,
            parameters={},
            seed=seed,
        )
