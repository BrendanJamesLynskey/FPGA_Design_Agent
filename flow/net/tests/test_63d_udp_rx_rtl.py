"""ip_lib/ipv4_udp_rx under cocotb + Icarus against its model at three points, and its elaboration guards.
NET_RTL_IPV4_UDP_RX points the tests at a seeded-fault copy (flow/net/faults.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import cocotb_run
from flow.net import sim

ROOT = Path(__file__).resolve().parents[3]
TB = ROOT / "ip_lib" / "ipv4_udp_rx" / "tb"
POINTS = {"p4_all": {"N_PORTS": 4, "CHECK_UDP": 1, "ACCEPT_BCAST": 1, "ACCEPT_MCAST": 1},
          "p1_nocheck_unicast": {"N_PORTS": 1, "CHECK_UDP": 0, "ACCEPT_BCAST": 0, "ACCEPT_MCAST": 0},
          "p8_mcast": {"N_PORTS": 8, "CHECK_UDP": 1, "ACCEPT_BCAST": 0, "ACCEPT_MCAST": 1}}


@pytest.mark.parametrize("point", sorted(POINTS))
def test_udp_rx(point):
    cocotb_run.run(f"udp_rx_{point}", "ipv4_udp_rx", sim.rtl("ipv4_udp_rx"), "udp_rx_cocotb", TB,
                   parameters=POINTS[point], extra_env={"PYTHONPATH": str(ROOT)})


@pytest.mark.parametrize("params", [{"N_PORTS": 0}, {"N_PORTS": 9}, {"CHECK_UDP": 2}, {"ACCEPT_BCAST": 2},
                                    {"ACCEPT_MCAST": 2}])
def test_udp_rx_guards(params):
    bad, out = sim.elaborate_fails(sim.rtl("ipv4_udp_rx"), "ipv4_udp_rx", params)
    assert bad, out
