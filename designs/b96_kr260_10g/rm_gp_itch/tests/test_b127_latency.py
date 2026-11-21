"""The latency stage file of build rm_gp_itch reconciles with the recorded simulations (brief 127): the stage clocks add up to what the whole-core xsim and the real-MAC bench measured."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from flow.latency import model as lm

DESIGN = Path(__file__).parent.parent
ROOT = DESIGN.parents[2]
CORE = ROOT / "results" / "b127" / "core_sim.json"
UNIT = ROOT / "results" / "b127" / "latency_sim.json"


@pytest.mark.skipif(not (CORE.exists() and UNIT.exists()), reason="the records of brief 127 are not there")
def test_stage_file_reconciles() -> None:
    r = lm.latency_path(DESIGN, json.loads(CORE.read_text()), path="itch_to_order", lat_sim=json.loads(UNIT.read_text()))
    assert r["reconciled"], r["problems"]
    assert r["total_clocks"] == sum(s["clocks"] for s in r["stages"])
