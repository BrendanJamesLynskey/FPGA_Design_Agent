import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flow import cocotb_run  # noqa: E402

PARAMS = dict(GATE_LEN_DEFAULT=2000, GATE_LEN_MIN=1000,
              LED_C3_HALF_PERIOD_CYCLES=40, LED_REF_HALF_PERIOD_CYCLES=250)


def test_p1_clkmeter_rtl():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    for seed in (1, 2, 3):
        cocotb_run.run("p1_clkmeter", "freq_meter_core", sources,
                       "bench_p1_clkmeter", DESIGN / "tests",
                       parameters=PARAMS, seed=seed)
