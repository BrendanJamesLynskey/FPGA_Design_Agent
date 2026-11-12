"""cocotb bench for ip_lib/ipv4_udp_tx against ip_lib/ipv4_udp_tx/model.py (RFC 791/768/1071), every frame also
decoded by scapy with both checksums recomputed from scratch (test time only). Random payload lengths up to and over
MAX_PAYLOAD, payloads whose checksum sums to zero, random destinations, input gaps and output back-pressure.
Environment: UTX_SEED, UTX_N."""
from __future__ import annotations

import os
import random
import struct

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge

from flow.net import inet
from flow.net.tests import axis_tb
from ip_lib.ipv4_udp_tx import model

SEED = int(os.environ.get("UTX_SEED", "1"))
N = int(os.environ.get("UTX_N", "40"))
OWN_MAC = inet.mac_b("02:00:00:00:00:01")
OWN_IP = inet.ip_b("192.168.10.2")
try:
    from scapy.layers.inet import IP, UDP
    from scapy.layers.l2 import Ether
    HAVE_SCAPY = True
except ImportError:
    HAVE_SCAPY = False


def scapy_check(fr: bytes, csum: bool):
    if not HAVE_SCAPY:
        return
    p = Ether(fr)
    ic, uc = p[IP].chksum, p[UDP].chksum
    del p[IP].chksum
    if csum:
        del p[UDP].chksum
    q = Ether(bytes(p))
    assert q[IP].chksum == ic and (not csum or q[UDP].chksum == uc), (hex(ic), hex(q[IP].chksum), hex(uc), hex(q[UDP].chksum))
    assert csum or uc == 0


def zero_sum_payload(sport, dport, dst, n=6):
    """A payload whose UDP checksum computes to 0 (it must go out as 0xFFFF): fix two bytes after the fact."""
    pay = bytearray(n)
    u = inet.udp(OWN_IP, dst, sport, dport, bytes(pay), checksum=False)
    s = 0xFFFF - inet.csum(OWN_IP + dst + struct.pack(">BBH", 0, 17, len(u)) + u)    # the ones' sum so far
    pay[0:2] = struct.pack(">H", (0xFFFF - s) & 0xFFFF or 0xFFFF)
    return bytes(pay)


@cocotb.test()
async def udp_tx(dut):
    maxp, cs, ttl = int(dut.MAX_PAYLOAD.value), int(dut.CSUM.value), int(dut.TTL.value)
    rng = random.Random(SEED + maxp)
    dut.own_mac.value = int.from_bytes(OWN_MAC, "big")
    dut.own_ip.value = int.from_bytes(OWN_IP, "big")
    await axis_tb.start(dut)
    src = axis_tb.Source(dut, rng, gap=0.2, user=False)
    sink = axis_tb.Sink(dut, rng, ready=0.7)
    n_ev = {"ev_sent": 0, "ev_too_long": 0}

    async def count():
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            for k in n_ev:
                n_ev[k] += int(getattr(dut, k).value)
    cocotb.start_soon(count())
    want, ident, zs = [], 0, 0
    for k in range(N):
        dst = rng.choice([inet.ip_b(f"192.168.10.{rng.randrange(3, 250)}"), inet.ip_b("239.1.2.3")])
        dmac = inet.mcast_mac(dst) if dst[0] >> 4 == 0xE else inet.mac_b(f"02:dd:00:00:00:{rng.randrange(256):02x}")
        sp, dp = rng.randrange(65536), rng.randrange(65536)
        u = rng.random()
        n = (maxp + rng.randrange(1, 4)) if u < 0.1 else maxp if u < 0.2 else rng.randrange(1, min(maxp, 600) + 1)
        pay = bytes(rng.randrange(256) for _ in range(n))
        if k % 9 == 4 and maxp >= 6:
            pay, n = zero_sum_payload(sp, dp, dst), 6
            zs += 1
        side = {"s_dst_mac": int.from_bytes(dmac, "big"), "s_dst_ip": int.from_bytes(dst, "big"), "s_src_port": sp,
                "s_dst_port": dp}
        if n <= maxp:
            want.append(model.frame(pay, OWN_MAC, OWN_IP, dmac, dst, sp, dp, ident, ttl, bool(cs)))
            ident += 1
        await src.send(pay, side=side)
        if rng.random() < 0.5:
            await axis_tb.clocks(dut, rng.randrange(1, 40))
    await axis_tb.clocks(dut, 2 * maxp + 2000)
    sink.stop()
    got = [f for f, _ in sink.frames]
    assert len(got) == len(want), (len(got), len(want))
    for k, (g, w) in enumerate(zip(got, want)):
        assert g == w, (k, len(g), len(w), g[:44].hex(), w[:44].hex())
        scapy_check(g, bool(cs))
    assert n_ev["ev_sent"] == len(want) and n_ev["ev_too_long"] == N - len(want), n_ev
    dut._log.info(f"udp_tx: {N} payloads, {len(want)} sent, {zs} with a zero checksum sum, events {n_ev}")
