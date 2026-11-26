import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402,F401
from flow import cocotb_run  # noqa: E402

DESIGN_DIR = Path(__file__).resolve().parents[1]
PARAMS = dict(GATE_LEN_DEFAULT=2000,
              LED_HALF_PERIOD_C3_CYCLES=16,
              LED_HALF_PERIOD_REF_CYCLES=125)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_p1_clkmeter_rtl(seed):
    sources = sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    cocotb_run.run("p1_clkmeter", "freq_meter_core", sources,
                   "bench_p1_clkmeter", DESIGN_DIR / "tests",
                   parameters=PARAMS, seed=seed)
