"""Brief 64A: bounded formal check of the generated blocks' AXI4-Lite slave rules (SymbiYosys, depth 20), the cover task
that shows a write and a read can complete, and two seeded handshake faults the proof must find."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hwsw import regmap
from hwsw.tests import regmap_formal

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "hwsw" / "examples" / "demo_accel.yaml"
STRESS = Path(__file__).parent / "data" / "stress.yaml"
OUT = ROOT / "build" / "64a" / "formal"
pytestmark = pytest.mark.skipif(not shutil.which("sby"), reason="needs sby, yosys and z3 on PATH")


@pytest.mark.parametrize("y", [DEMO, STRESS], ids=["demo_accel", "stress"])
@pytest.mark.parametrize("mode", ["bmc", "cover"])
def test_slave_rules_hold(y: Path, mode: str) -> None:
    m = regmap.load(y)
    assert regmap_formal.run(y, OUT / f"{m.name}_{mode}", mode, 20) == "PASS"


FAULTS = [
    ("b_before_w", "assign wr_commit      = aw_got && w_got && !s_axil_bvalid;",
     "assign wr_commit      = aw_got && !s_axil_bvalid;"),
    ("r_dropped_early", "end else if (s_axil_rvalid && s_axil_rready) begin\n            s_axil_rvalid <= 1'b0;",
     "end else if (s_axil_rvalid) begin\n            s_axil_rvalid <= 1'b0;"),
]


@pytest.mark.parametrize("fid,old,new", FAULTS, ids=[f[0] for f in FAULTS])
def test_seeded_handshake_fault_is_found(fid: str, old: str, new: str) -> None:
    m = regmap.load(DEMO)
    good = regmap.emit_sv(m)
    assert good.count(old) == 1
    assert regmap_formal.run(DEMO, OUT / f"fault_{fid}", "bmc", 20, sv_text=good.replace(old, new)) == "FAIL"
