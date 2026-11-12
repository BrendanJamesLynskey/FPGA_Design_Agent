"""ip_lib/icmp_echo under cocotb + Icarus against its model at three points (both buffer variants), and its
elaboration guards. NET_RTL_ICMP_ECHO points the tests at a seeded-fault copy (flow/net/faults.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import cocotb_run
from flow.net import sim

ROOT = Path(__file__).resolve().parents[3]
TB = ROOT / "ip_lib" / "icmp_echo" / "tb"
POINTS = {"bram_2048": {"BUF_BYTES": 2048, "TTL": 64, "RAM": '"bram"'},
          "lutram_128": {"BUF_BYTES": 128, "TTL": 255, "RAM": '"lutram"'},
          "bram_16384": {"BUF_BYTES": 16384, "TTL": 128, "RAM": '"bram"'}}


@pytest.mark.parametrize("point", sorted(POINTS))
def test_icmp(point):
    cocotb_run.run(f"icmp_{point}", "icmp_echo", sim.rtl("icmp_echo"), "icmp_cocotb", TB, parameters=POINTS[point],
                   extra_env={"PYTHONPATH": str(ROOT)})


@pytest.mark.parametrize("params", [{"BUF_BYTES": 100}, {"BUF_BYTES": 64}, {"BUF_BYTES": 32768}, {"TTL": 0},
                                    {"TTL": 256}, {"RAM": '"uram"'}])
def test_icmp_guards(params):
    bad, out = sim.elaborate_fails(sim.rtl("icmp_echo"), "icmp_echo", params)
    assert bad, out
