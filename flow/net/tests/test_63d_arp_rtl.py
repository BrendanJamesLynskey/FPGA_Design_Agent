"""ip_lib/arp_responder under cocotb + Icarus against its model (RFC 826) at three cache sizes, and its elaboration
guards. NET_RTL_ARP_RESPONDER points the tests at a seeded-fault copy (flow/net/faults.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import cocotb_run
from flow.net import sim

ROOT = Path(__file__).resolve().parents[3]
TB = ROOT / "ip_lib" / "arp_responder" / "tb"
POINTS = {"cache4": {"CACHE_N": 4, "HOLDOFF": 100}, "cache1": {"CACHE_N": 1, "HOLDOFF": 40},
          "cache16": {"CACHE_N": 16, "HOLDOFF": 200}}


@pytest.mark.parametrize("point", sorted(POINTS))
def test_arp(point):
    cocotb_run.run(f"arp_{point}", "arp_responder", sim.rtl("arp_responder"), "arp_cocotb", TB, parameters=POINTS[point],
                   extra_env={"PYTHONPATH": str(ROOT)})


@pytest.mark.parametrize("params", [{"CACHE_N": 0}, {"CACHE_N": 17}, {"HOLDOFF": 0}, {"HOLDOFF": 16777216}])
def test_arp_guards(params):
    bad, out = sim.elaborate_fails(sim.rtl("arp_responder"), "arp_responder", params)
    assert bad, out
