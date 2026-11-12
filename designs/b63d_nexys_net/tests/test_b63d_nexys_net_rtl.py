"""pytest entry: b63d_nexys_net_top under cocotb + Icarus (shell at 8 clocks a bit, a model RMII PHY)."""
from __future__ import annotations

from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
DESIGN = HERE.parent
ROOT = DESIGN.parents[1]
IP = ROOT / "ip_lib"


def test_nexys_net() -> None:
    sources = (cocotb_run.SHELL_RTL + [ROOT / "designs" / "b30_hil_audio" / "tests" / "xadc_sim.sv"] +
               sorted((IP / "eth_mac_rmii" / "rtl").glob("*.sv")) +
               [IP / "eth_mac_rgmii" / "rtl" / "eth_rx_classify.sv", IP / "eth_mac_rgmii" / "rtl" / "eth_mac_stats.sv"] +
               [f for b in ("arp_responder", "icmp_echo", "igmp_join", "ipv4_udp_rx", "ipv4_udp_tx", "mdio_master")
                for f in sorted((IP / b / "rtl").glob("*.sv"))] +
               sorted((DESIGN / "rtl").glob("*.sv")))
    cocotb_run.run("b63d_nexys_net", "b63d_nexys_net_top", sources, "nexys_net_cocotb", HERE,
                   parameters={"CLKS_PER_BIT": 8, "TIMEOUT_CYCLES": 400, "TICK_CLKS": 200, "ARP_HOLDOFF": 1000},
                   extra_env={"PYTHONPATH": str(ROOT)}, seed=1)
