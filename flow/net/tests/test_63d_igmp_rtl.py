"""ip_lib/igmp_join under cocotb + Icarus against RFC 2236 (ip_lib/igmp_join/model.py) at three points, and its
elaboration guards. NET_RTL_IGMP_JOIN points the tests at a seeded-fault copy (flow/net/faults.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import cocotb_run
from flow.net import sim

ROOT = Path(__file__).resolve().parents[3]
TB = ROOT / "ip_lib" / "igmp_join" / "tb"
POINTS = {"g4": {"N_GROUPS": 4, "TICK_CLKS": 40, "UNSOL_TICKS": 10},
          "g1": {"N_GROUPS": 1, "TICK_CLKS": 25, "UNSOL_TICKS": 1},
          "g8": {"N_GROUPS": 8, "TICK_CLKS": 60, "UNSOL_TICKS": 20}}


@pytest.mark.parametrize("point", sorted(POINTS))
def test_igmp(point):
    cocotb_run.run(f"igmp_{point}", "igmp_join", sim.rtl("igmp_join"), "igmp_cocotb", TB, parameters=POINTS[point],
                   extra_env={"PYTHONPATH": str(ROOT)})


@pytest.mark.parametrize("params", [{"N_GROUPS": 0}, {"N_GROUPS": 9}, {"TICK_CLKS": 0}, {"UNSOL_TICKS": 0},
                                    {"UNSOL_TICKS": 256}])
def test_igmp_guards(params):
    bad, out = sim.elaborate_fails(sim.rtl("igmp_join"), "igmp_join", params)
    assert bad, out
