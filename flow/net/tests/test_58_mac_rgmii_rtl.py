"""pytest entry: ip_lib/eth_mac_rgmii under cocotb + Icarus at several parameter points, and its
elaboration guards. NET_RTL_ETH_MAC_RGMII points the tests at a seeded-fault copy (flow/net/faults.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from flow import cocotb_run
from flow.net import sim

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CRC = ROOT / "ip_lib" / "eth_mac_rmii" / "rtl" / "eth_crc32.sv"
XPM = ROOT / "flow" / "cdc_models" / "xpm_cdc_models.sv"
PKG = ROOT / "flow" / "cdc_models" / "cdc_inj_pkg.sv"


def srcs() -> list[Path]:
    return [CRC] + sim.rtl("eth_mac_rgmii")


POINTS = {
    "ct_1000_100_10": ({"CUT_THROUGH": 1}, "2,1,0", "receive,transmit"),
    "sf_1000_100": ({"CUT_THROUGH": 0, "SF_DEPTH": 4096}, "2,1", "receive"),
    "sf_small": ({"CUT_THROUGH": 0, "SF_DEPTH": 2048, "MIN_FRAME": 60, "MAX_FRAME": 1000, "MIN_DATA": 46,
                  "IFG_BYTES": 16}, "2", "receive,transmit"),
}


@pytest.mark.parametrize("point", sorted(POINTS))
def test_mac_rgmii(point: str) -> None:
    params, speeds, tests = POINTS[point]
    cocotb_run.run(f"mac_rgmii_{point}", "eth_mac_rgmii", srcs(), "mac_rgmii_cocotb", HERE, parameters=params,
                   testcase=tests.split(","), extra_env={"MAC_SPEEDS": speeds, "PYTHONPATH": str(ROOT)})


@pytest.mark.parametrize("params", [{"CUT_THROUGH": 2}, {"MIN_FRAME": 17}, {"MAX_FRAME": 2001},
                                    {"CUT_THROUGH": 0, "SF_DEPTH": 3000}, {"MIN_DATA": 0}, {"IFG_BYTES": 0}])
def test_mac_rgmii_guards(params):
    bad, out = sim.elaborate_fails([PKG, XPM] + srcs(), "eth_mac_rgmii", params)
    assert bad, out
