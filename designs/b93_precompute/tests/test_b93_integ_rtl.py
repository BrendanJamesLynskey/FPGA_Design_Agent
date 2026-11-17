"""pytest entry: the 58A trigger_core with the decision model, baseline and precomputed (cocotb + Icarus).

    B93_ML_ARM=1|4 B93_ML_PRE=0|1|2|3 [B93_RECORD=<abs dir>] pytest designs/b93_precompute/tests/test_b93_integ_rtl.py

ML_ARM 1 = 87 boosted trees, 4 = 89 lg_small; ML_PRE 0 = the 87 path, 1 = early features, 2/3 = early features and the
partial-evaluation block (table fill 1 / 2 clocks). B93_RECORD writes integration_<arm>_pre<N>_{latency,twin}.json."""
from __future__ import annotations

import os
from pathlib import Path

from designs.b58a_trigger.tests.test_b58a_rtl import SOURCES
from flow import cocotb_run

HERE = Path(__file__).parent
D = HERE.parent
ROOT = HERE.parents[2]
ML_ARM = int(os.environ.get("B93_ML_ARM", "1"))
ML_PRE = int(os.environ.get("B93_ML_PRE", "0"))
ARM_SRC = {1: ROOT / "designs/b87_ml_trading/rtl/gen/gbt_comb.sv", 4: ROOT / "designs/b89_lutnet_gen/rtl/gen/lg_small_comb.sv"}
PE_SRC = {(1, 2): "gbt_pe", (1, 3): "gbt_pe2", (4, 2): "lgs_pe", (4, 3): "lgs_pe2"}


def test_b93_integration() -> None:
    env = {"PYTHONPATH": str(ROOT), "B93_ML_ARM": str(ML_ARM), "B93_ML_PRE": str(ML_PRE)}
    rec = os.environ.get("B93_RECORD")
    tag = f"{'gbt' if ML_ARM == 1 else 'lgs'}_pre{ML_PRE}"
    if rec:
        Path(rec).mkdir(parents=True, exist_ok=True)
        env |= {"B93_INTEG_OUT": str(Path(rec) / f"integration_{tag}_latency.json"),
                "B93_TWIN_OUT": str(Path(rec) / f"integration_{tag}_twin.json")}
    b87 = ROOT / "designs/b87_ml_trading/rtl"
    model = ARM_SRC[ML_ARM] if ML_PRE <= 1 else D / "rtl" / "gen" / f"{PE_SRC[(ML_ARM, ML_PRE)]}.sv"
    srcs = SOURCES[:-1] + [b87 / "ml_feat.sv", b87 / "ml_gate.sv", D / "rtl" / "ml_feat_pre.sv", D / "rtl" / "ml_gate_pre.sv",
                           model] + SOURCES[-1:]
    cocotb_run.run(f"b93_integ_{tag}", "trigger_core", srcs, "b93_integ_cocotb", HERE,
                   parameters={"BUILD_MODE": 0, "MDIO_DIV": 4, "ML_ARM": ML_ARM, "ML_PRE": ML_PRE}, extra_env=env)


def test_gate_pre_timing_and_veto() -> None:
    """ml_gate_pre alone: the class before, with and after the rule's decision."""
    cocotb_run.run("b93_gate_pre", "ml_gate_pre", [D / "rtl" / "ml_gate_pre.sv"], "b93_gate_cocotb", HERE,
                   parameters={"FW": 8}, extra_env={"PYTHONPATH": str(ROOT)})
