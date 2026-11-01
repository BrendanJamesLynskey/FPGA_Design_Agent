"""pytest entry for T1's V2 run: the existing directed tests plus t1_verif, once per seed, under $SIM
(icarus by default; verilator 5.036+ with checkers bound and code coverage on).

    SIM=verilator T1_SEEDS=1,2,3 pytest designs/t1_dimmer_counter/tests/test_t1_verif_rtl.py

Outputs under build/verif/<sim>/: seed<N>/{sim.log,results.xml,coverage.dat} and seed<N>/coverage_t1.yml.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]
PARAMS = {"CLKS_PER_BIT": 8, "TIMEOUT_CYCLES": 400, "DEBOUNCE_CYCLES": 20, "PWM_PRESCALE": 4, "REFRESH_BITS": 3}
SEEDS = [int(s) for s in os.environ.get("T1_SEEDS", "1,2,3").split(",")]
SIM = os.environ.get("SIM", "icarus")
TAG = os.environ.get("T1_RUN_TAG", "")           # flow/mutate.py keeps each mutant's outputs apart


@pytest.mark.parametrize("seed", SEEDS)
def test_t1_v2_run(seed: int) -> None:
    rtl = Path(os.environ.get("T1_RTL_DIR", DESIGN / "rtl"))
    sources = cocotb_run.SHELL_RTL + sorted(rtl.glob("*.sv"))
    if SIM == "verilator":                          # Icarus has no bind and no concurrent assertions
        sources += sorted((DESIGN / "verif" / "checkers").glob("*.sv"))
        sources = [s for s in sources if s.name != "t1_bind.sv"] + [DESIGN / "verif" / "checkers" / "t1_bind.sv"]
    out = ROOT / "build" / "verif" / f"{SIM}{TAG}" / f"seed{seed}"
    cocotb_run.run(f"{SIM}{TAG}/seed{seed}", "t1_dimmer_counter_top", sources, ["t1_cocotb", "t1_verif"], HERE,
                   parameters=PARAMS, seed=seed, build_root=ROOT / "build" / "verif", extra_env={"T1_COV_OUT": str(out / "coverage_t1.yml")},
                   coverage=(SIM == "verilator"))
