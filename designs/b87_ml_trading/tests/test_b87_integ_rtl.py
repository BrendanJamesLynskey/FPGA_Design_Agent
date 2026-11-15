"""pytest entry: the 58A trigger_core with the decision model behind the rules (cocotb + Icarus).

B87_RECORD=<dir> writes integration_latency_sim.json and integration_twin_sim.json there."""
from __future__ import annotations

import os
from pathlib import Path

from designs.b58a_trigger.tests.test_b58a_rtl import SOURCES
from flow import cocotb_run

HERE = Path(__file__).parent
RTL = HERE.parent / "rtl"
ARM = {1: "gbt_comb", 2: "lutnet", 3: "mlp_hand"}
ML_ARM = int(os.environ.get("B87_ML_ARM", "1"))


def test_b87_integration() -> None:
    env = {"PYTHONPATH": str(HERE.parents[2]), "B87_ML_ARM": str(ML_ARM)}
    rec = os.environ.get("B87_RECORD")
    if rec:
        Path(rec).mkdir(parents=True, exist_ok=True)
        env |= {"B87_INTEG_OUT": str(Path(rec) / "integration_latency_sim.json"),
                "B87_TWIN_OUT": str(Path(rec) / "integration_twin_sim.json")}
    srcs = SOURCES[:-1] + [RTL / "ml_feat.sv", RTL / "ml_gate.sv", RTL / "gen" / f"{ARM[ML_ARM]}.sv"] + SOURCES[-1:]
    cocotb_run.run(f"b87_integ_{ML_ARM}", "trigger_core", srcs, "b87_integ_cocotb", HERE,
                   parameters={"BUILD_MODE": 0, "MDIO_DIV": 4, "ML_ARM": ML_ARM}, extra_env=env)
