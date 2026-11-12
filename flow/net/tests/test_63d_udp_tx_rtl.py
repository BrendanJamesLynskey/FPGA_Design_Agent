"""ip_lib/ipv4_udp_tx under cocotb + Icarus against its model at three points (both buffer variants), and its
elaboration guards. NET_RTL_IPV4_UDP_TX points the tests at a seeded-fault copy (flow/net/faults.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import cocotb_run
from flow.net import sim

ROOT = Path(__file__).resolve().parents[3]
TB = ROOT / "ip_lib" / "ipv4_udp_tx" / "tb"
POINTS = {"bram_1472": {"MAX_PAYLOAD": 1472, "CSUM": 1, "TTL": 64, "RAM": '"bram"'},
          "lutram_64_nocsum": {"MAX_PAYLOAD": 64, "CSUM": 0, "TTL": 1, "RAM": '"lutram"'},
          "bram_8972": {"MAX_PAYLOAD": 8972, "CSUM": 1, "TTL": 255, "RAM": '"bram"'}}


@pytest.mark.parametrize("point", sorted(POINTS))
def test_udp_tx(point):
    cocotb_run.run(f"udp_tx_{point}", "ipv4_udp_tx", sim.rtl("ipv4_udp_tx"), "udp_tx_cocotb", TB,
                   parameters=POINTS[point], extra_env={"PYTHONPATH": str(ROOT)})


@pytest.mark.parametrize("params", [{"MAX_PAYLOAD": 0}, {"MAX_PAYLOAD": 8973}, {"CSUM": 2}, {"TTL": 0}, {"TTL": 256},
                                    {"RAM": '"uram"'}])
def test_udp_tx_guards(params):
    bad, out = sim.elaborate_fails(sim.rtl("ipv4_udp_tx"), "ipv4_udp_tx", params)
    assert bad, out
