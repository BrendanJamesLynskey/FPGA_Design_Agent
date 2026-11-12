"""cocotb bench for ip_lib/arp_responder against ip_lib/arp_responder/model.py (RFC 826), with scapy as a second,
independent decoder of every frame the block sends (test time only). Random requests, replies, probes, malformed
packets, lookups and flushes, under random input gaps and output back-pressure; then the directed cases: a reply
dropped when two are already queued, and the request holdoff. Environment: ARP_SEED, ARP_N."""
from __future__ import annotations

import os
import random

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge, Timer

from flow.net import inet
from flow.net.tests import axis_tb
from ip_lib.arp_responder import model

SEED = int(os.environ.get("ARP_SEED", "1"))
N = int(os.environ.get("ARP_N", "150"))
OWN_MAC = inet.mac_b("02:00:00:00:00:01")
OWN_IP = inet.ip_b("192.168.10.2")

try:
    from scapy.layers.l2 import ARP, Ether
    HAVE_SCAPY = True
except ImportError:                 # the bench still runs; only the second decoder is skipped
    HAVE_SCAPY = False


def scapy_check(fr: bytes):
    if not HAVE_SCAPY:
        return
    p = Ether(fr)
    assert p.type == 0x0806 and ARP in p and p[ARP].hwtype == 1 and p[ARP].ptype == 0x0800
    assert p[ARP].hwsrc == "02:00:00:00:00:01" and p[ARP].psrc == "192.168.10.2"


class Events:
    def __init__(self, dut):
        self.n = {k: 0 for k in ("ev_rx_request", "ev_rx_reply", "ev_tx_reply", "ev_tx_request", "ev_learn", "ev_drop")}
        cocotb.start_soon(self.run(dut))

    async def run(self, dut):
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            for k in self.n:
                self.n[k] += int(getattr(dut, k).value)


async def lookup(dut, ip: bytes):
    dut.lk_valid.value = 1
    dut.lk_ip.value = int.from_bytes(ip, "big")
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.lk_valid.value = 0
    await ReadOnly()
    assert int(dut.lk_done.value) == 1
    hit, mac = int(dut.lk_hit.value), int(dut.lk_mac.value).to_bytes(6, "big")
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    return bool(hit), mac


@cocotb.test()
async def arp(dut):
    cache_n, holdoff = int(dut.CACHE_N.value), int(dut.HOLDOFF.value)
    rng = random.Random(SEED + cache_n)
    dut.own_mac.value = int.from_bytes(OWN_MAC, "big")
    dut.own_ip.value = int.from_bytes(OWN_IP, "big")
    dut.lk_valid.value = 0
    dut.lk_ip.value = 0
    dut.flush.value = 0
    await axis_tb.start(dut)
    src = axis_tb.Source(dut, rng, gap=0.2)
    sink = axis_tb.Sink(dut, rng, ready=0.7)
    ev = Events(dut)
    m = model.Arp(OWN_MAC, OWN_IP, cache_n)
    hosts = [(inet.mac_b(f"02:aa:00:00:00:{i:02x}"), inet.ip_b(f"192.168.10.{10 + i}")) for i in range(24)]
    want: list[bytes] = []
    for step in range(N):
        u = rng.random()
        h = rng.choice(hosts)
        if u < 0.65:
            if u < 0.25:
                pkt = inet.arp(1, h[0], h[1], b"\x00" * 6, OWN_IP)                         # a request for us
            elif u < 0.35:
                pkt = inet.arp(1, h[0], h[1], b"\x00" * 6, rng.choice(hosts)[1])           # for someone else
            elif u < 0.45:
                pkt = inet.arp(2, h[0], h[1], OWN_MAC, OWN_IP)                             # a reply to us
            elif u < 0.5:
                pkt = inet.arp(1, h[0], b"\x00" * 4, b"\x00" * 6, OWN_IP)                  # a probe
            elif u < 0.55:
                pkt = inet.arp(1, h[0], h[1], b"\x00" * 6, OWN_IP)
                pkt = pkt[:4] + b"\x08" + pkt[5:]                                          # hardware length 8
            else:
                pkt = inet.arp(rng.choice([1, 2]), rng.choice(hosts)[0], h[1], OWN_MAC, OWN_IP)    # a host moved
            dst = model.BCAST if pkt[7] == 1 else OWN_MAC
            fr = inet.eth(dst, h[0], 0x0806, pkt)
            pad = rng.random() < 0.5
            if pad:
                fr = fr.ljust(60, b"\x00")
            bad = rng.random() < 0.05
            short = rng.random() < 0.03
            if short:
                fr = fr[:41]
            want += m.rx(fr, bad)
            await src.send(fr, bad=bad)
        elif u < 0.95:
            ip = rng.choice(hosts)[1] if rng.random() < 0.8 else inet.ip_b(f"10.0.0.{rng.randrange(256)}")
            hit, mac = await lookup(dut, ip)
            mh, mm = m.lookup(ip)
            assert hit == mh and (not hit or mac == mm), (step, ip.hex(), hit, mac.hex(), mh, mm)
            if not hit:
                want.append(model.request(OWN_MAC, OWN_IP, ip))
        else:
            dut.flush.value = 1
            await RisingEdge(dut.clk)
            await Timer(1, unit="ns")
            dut.flush.value = 0
            m.flush()
        await axis_tb.clocks(dut, max(150, holdoff + 2))
    await axis_tb.clocks(dut, 400)
    got = [f for f, _ in sink.frames]
    assert len(got) == len(want), (len(got), len(want))
    for k, (g, w) in enumerate(zip(got, want)):
        assert g == w, (k, g.hex(), w.hex())
        scapy_check(g)
    assert ev.n["ev_drop"] == 0
    dut._log.info(f"arp: {N} steps, {len(got)} frames sent, events {ev.n}")

    # directed: back-pressure holds the first reply in the output and the second waits; the third is dropped
    sink.ready = 0.0
    await axis_tb.clocks(dut, 5)
    n0 = len(sink.frames)
    for h in hosts[:3]:
        await src.send(inet.eth(model.BCAST, h[0], 0x0806, inet.arp(1, h[0], h[1], b"\x00" * 6, OWN_IP)))
        await axis_tb.clocks(dut, 10)
    sink.ready = 1.0
    await axis_tb.clocks(dut, 300)
    assert [f for f, _ in sink.frames[n0:]] == [model.reply(OWN_MAC, OWN_IP, {"sha": h[0], "spa": h[1]})
                                                for h in hosts[:2]]
    assert ev.n["ev_drop"] == 1

    # directed: holdoff - two misses for one address within HOLDOFF clocks send one request
    n0 = len(sink.frames)
    ip = inet.ip_b("10.9.9.9")
    await lookup(dut, ip)
    await axis_tb.clocks(dut, 60)                    # the first request has left
    await lookup(dut, ip)
    await axis_tb.clocks(dut, holdoff + 60)
    await lookup(dut, ip)
    await axis_tb.clocks(dut, 100)
    reqs = [f for f, _ in sink.frames[n0:]]
    want_n = 1 if holdoff > 61 else 2
    assert len(reqs) == want_n + 1 and all(r == model.request(OWN_MAC, OWN_IP, ip) for r in reqs), len(reqs)
    sink.stop()
