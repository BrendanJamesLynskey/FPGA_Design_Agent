"""ip_lib/sg_dma under cocotb + Icarus: the engine against the memory model of tb/sg_dma_cocotb.py (data, bursts, 4 KB rule, ring wrap, back
pressure, errors, bad descriptors, interrupts, registers), at several (DIR, DATA_W, MAX_BURST, OUTSTANDING); the elaboration guards.
NET_RTL_SG_DMA points the tests at a seeded-fault copy of the RTL (flow/net/faults.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import cocotb_run
from flow.net import sim

ROOT = Path(__file__).resolve().parents[3]
TB = ROOT / "ip_lib" / "sg_dma" / "tb"

# (DIR, DATA_W, MAX_BURST, OUTSTANDING, ADDR_W)
POINTS = [(0, 32, 16, 4, 32), (1, 32, 16, 4, 32), (0, 64, 8, 2, 32), (1, 64, 8, 2, 32), (0, 128, 4, 1, 40), (1, 128, 4, 8, 40),
          (0, 32, 1, 1, 32), (1, 32, 256, 16, 32), (0, 64, 256, 3, 32), (1, 64, 3, 4, 32)]
TESTS = ["basic", "backpressure", "errors", "bad_descriptors", "interrupts", "registers"]


def _run(p, tests, extra=None):
    d, w, mb, oc, aw = p
    srcs = sim.rtl("sg_dma")
    cocotb_run.run(f"sg_dma_d{d}_w{w}_b{mb}_o{oc}_a{aw}", "sg_dma", srcs, "sg_dma_cocotb", TB,
                   parameters={"DIR": d, "DATA_W": w, "MAX_BURST": mb, "OUTSTANDING": oc, "ADDR_W": aw}, testcase=tests,
                   extra_env={"PYTHONPATH": str(ROOT), **(extra or {})})


@pytest.mark.parametrize("p", POINTS)
def test_engine(p):
    _run(p, TESTS)


@pytest.mark.parametrize("params", [{"DATA_W": 16}, {"DATA_W": 256}, {"ADDR_W": 31}, {"ADDR_W": 65}, {"MAX_BURST": 0}, {"MAX_BURST": 257},
                                    {"OUTSTANDING": 0}, {"OUTSTANDING": 17}, {"DIR": 2}])
def test_guards(params):
    bad, out = sim.elaborate_fails(sim.rtl("sg_dma"), "sg_dma", params)
    assert bad, out
