"""Adversarial benches from the independent review of the 63D entries (flow/net/tests/adversarial): expectations built
by scapy from the standards, not by the entries' own models. They cover cases the entries' benches did not: ICMP
odd lengths, last fragments and back-to-back frames; UDP last fragments, IHL 15 and odd checksums; IGMP report timing
and v1 queries; ARP gratuitous packets, probes and address conflicts; a pause received mid-frame and a zero-quanta
pause ending a long one. NET_RTL_<BLOCK> points them at a seeded-fault copy (flow/net/faults.py)."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import cocotb_run
from flow.net import sim, traffic

pytestmark = pytest.mark.skipif(not traffic.HAVE_SCAPY, reason="scapy not installed")
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent / "adversarial"
ENV = {"PYTHONPATH": f"{ROOT}:{HERE}"}


def test_adv_icmp():
    cocotb_run.run("adv_icmp", "icmp_echo", sim.rtl("icmp_echo"), "adv_icmp", HERE,
                   parameters={"BUF_BYTES": 2048, "TTL": 64}, extra_env=ENV)


def test_adv_udprx():
    cocotb_run.run("adv_udprx", "ipv4_udp_rx", sim.rtl("ipv4_udp_rx"), "adv_udprx", HERE, parameters={"N_PORTS": 1},
                   extra_env=ENV)


def test_adv_udptx():
    cocotb_run.run("adv_udptx", "ipv4_udp_tx", sim.rtl("ipv4_udp_tx"), "adv_udptx", HERE,
                   parameters={"MAX_PAYLOAD": 1472, "CSUM": 1, "TTL": 64}, extra_env=ENV)


def test_adv_igmp():
    cocotb_run.run("adv_igmp", "igmp_join", sim.rtl("igmp_join"), "adv_igmp", HERE,
                   parameters={"N_GROUPS": 2, "TICK_CLKS": 4, "UNSOL_TICKS": 10}, extra_env=ENV)


def test_adv_arp():
    cocotb_run.run("adv_arp", "arp_responder", sim.rtl("arp_responder"), "adv_arp", HERE,
                   parameters={"CACHE_N": 2, "HOLDOFF": 50}, extra_env=ENV)


def test_adv_pause():
    crc = ROOT / "ip_lib" / "eth_mac_rmii" / "rtl" / "eth_crc32.sv"
    xpm = ROOT / "flow" / "cdc_models" / "xpm_cdc_models.sv"
    pkg = ROOT / "flow" / "cdc_models" / "cdc_inj_pkg.sv"
    cocotb_run.run("adv_pause", "eth_mac_rgmii", [pkg, xpm, crc] + sim.rtl("eth_mac_rgmii"), "adv_pause", HERE,
                   parameters={"CUT_THROUGH": 1, "PAUSE": 1, "FILTER": 1, "STATS": 1}, extra_env=ENV)
