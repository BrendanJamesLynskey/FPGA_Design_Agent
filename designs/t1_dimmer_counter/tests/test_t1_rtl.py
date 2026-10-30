"""pytest entry: T1's board top under cocotb + Icarus, checked against model.py."""

from __future__ import annotations

import os
from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
TEST_PARAMS = {"CLKS_PER_BIT": 8, "TIMEOUT_CYCLES": 400, "DEBOUNCE_CYCLES": 20, "PWM_PRESCALE": 4,
               "REFRESH_BITS": 3}


def test_t1_against_model() -> None:
    # T1_RTL_DIR lets tests/run_mutants.sh point the same tests at a broken copy of the RTL
    rtl = Path(os.environ.get("T1_RTL_DIR", DESIGN / "rtl"))
    sources = cocotb_run.SHELL_RTL + sorted(rtl.glob("*.sv"))
    cocotb_run.run(os.environ.get("T1_SIM_NAME", "t1_dimmer_counter"), "t1_dimmer_counter_top", sources,
                   "t1_cocotb", HERE, parameters=TEST_PARAMS, seed=int(os.environ.get("T1_SEED", "1")))
