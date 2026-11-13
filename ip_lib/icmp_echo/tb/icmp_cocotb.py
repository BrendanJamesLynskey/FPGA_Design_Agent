"""cocotb bench for ip_lib/icmp_echo against ip_lib/icmp_echo/model.py (RFC 792/791/1122; the model computes the
reply's checksums from scratch, the RTL updates them incrementally), with scapy as an independent decoder of every
reply (test time only). Random echo requests of many lengths, with Ethernet padding, and the cases that must not be
answered (other address, bad checksums, fragments, options, other ICMP types, a bad or truncated frame, too long),
under random input gaps and output back-pressure; then a request arriving while a reply waits. Environment:
ICMP_SEED, ICMP_N."""
from __future__ import annotations

import os
import random
import struct

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge

from flow.net import inet
from flow.net.tests import axis_tb
from ip_lib.icmp_echo import model

SEED = int(os.environ.get("ICMP_SEED", "1"))
N = int(os.environ.get("ICMP_N", "60"))
LATENCY = 4                                         # ip.yaml latency.reply
OWN_MAC = inet.mac_b("02:00:00:00:00:01")
OWN_IP = inet.ip_b("192.168.10.2")
try:
    from scapy.layers.inet import ICMP, IP
    from scapy.layers.l2 import Ether
    HAVE_SCAPY = True
except ImportError:
    HAVE_SCAPY = False


def scapy_check(rep: bytes, req: bytes, ttl: int):
    if not HAVE_SCAPY:
        return
    p, q = Ether(rep), Ether(req)
    assert p[IP].src == q[IP].dst and p[IP].dst == q[IP].src and p[IP].ttl == ttl
    assert p[ICMP].type == 0 and p[ICMP].id == q[ICMP].id and p[ICMP].seq == q[ICMP].seq
    assert bytes(p[IP])[28:p[IP].len] == bytes(q[IP])[28:q[IP].len]      # the data, Ethernet padding aside
    ic, ih = p[ICMP].chksum, p[IP].chksum
    del p[ICMP].chksum, p[IP].chksum
    p2 = Ether(bytes(p))                             # scapy recomputes both checksums from scratch
    assert p2[ICMP].chksum == ic and p2[IP].chksum == ih, (hex(ic), hex(p2[ICMP].chksum), hex(ih), hex(p2[IP].chksum))


class Counts:
    def __init__(self, dut):
        self.n = {k: 0 for k in ("ev_request", "ev_reply", "ev_busy", "ev_bad")}
        cocotb.start_soon(self.run(dut))

    async def run(self, dut):
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            for k in self.n:
                self.n[k] += int(getattr(dut, k).value)


def make(rng: random.Random, buf: int):
    """(frame, tuser, kind)"""
    host = inet.mac_b(f"02:bb:00:00:00:{rng.randrange(256):02x}")
    hip = inet.ip_b(f"192.168.10.{rng.randrange(3, 250)}")
    big = rng.random() < 0.15
    n = rng.randrange(0, min(buf, 9000)) if big else rng.choice([0, 1, 7, 17, 18, 32, 56, 57, 100, 300])
    data = bytes(rng.randrange(256) for _ in range(n))
    fr = model.request(host, OWN_MAC, hip, OWN_IP, rng.randrange(65536), rng.randrange(65536), data,
                       ttl=rng.randrange(1, 256), ip_ident=rng.randrange(65536), df=rng.random() < 0.5)
    kind = rng.choice(["ok"] * 8 + ["dst", "ipcs", "icmpcs", "frag", "opts", "type", "code", "bad", "trunc"])
    b = bytearray(fr)
    if kind == "dst":
        b = bytearray(model.request(host, OWN_MAC, hip, inet.ip_b("192.168.10.3"), 1, 1, data))
    elif kind == "ipcs":
        b[24] ^= 0x10
    elif kind == "icmpcs":
        b[36] ^= 0x01
    elif kind == "frag":
        b[20] |= 0x20                                    # MF
        b[24:26] = b"\x00\x00"; b[24:26] = struct.pack(">H", inet.csum(bytes(b[14:34])))
    elif kind == "opts":
        icmp = bytes(b[34:])
        b = bytearray(inet.eth(OWN_MAC, host, 0x0800, inet.ipv4(hip, OWN_IP, 1, icmp, options=b"\x01\x01\x01\x00")))
    elif kind == "type":
        b[34] = 13                                       # timestamp request
        b[36:38] = b"\x00\x00"; b[36:38] = struct.pack(">H", inet.csum(bytes(b[34:])))
    elif kind == "code":
        b[35] = 1
        b[36:38] = b"\x00\x00"; b[36:38] = struct.pack(">H", inet.csum(bytes(b[34:])))
    elif kind == "trunc":
        b = b[:len(b) - 1 - rng.randrange(min(5, len(b) - 40))]
    fr = bytes(b)
    if len(fr) < 60:
        if rng.random() < 0.8:                           # Ethernet padding, mostly; zeros or (allowed) anything
            fr += bytes(rng.randrange(256) if rng.random() < 0.5 else 0 for _ in range(60 - len(fr)))
    return fr, kind == "bad", kind


@cocotb.test()
async def echo(dut):
    buf, ttl = int(dut.BUF_BYTES.value), int(dut.TTL.value)
    rng = random.Random(SEED + buf)
    dut.own_mac.value = int.from_bytes(OWN_MAC, "big")
    dut.own_ip.value = int.from_bytes(OWN_IP, "big")
    await axis_tb.start(dut)
    src = axis_tb.Source(dut, rng, gap=0.2)
    sink = axis_tb.Sink(dut, rng, ready=0.7)
    ev = Counts(dut)
    want, reqs, kinds = [], [], {}
    for _ in range(N):
        fr, bad, kind = make(rng, buf)
        rep, why = model.reply(fr, OWN_MAC, OWN_IP, ttl, buf, bad)
        key = kind if rep or kind != "ok" else "ok_too_long"
        kinds[key] = kinds.get(key, 0) + 1
        if rep:
            want.append(rep); reqs.append(fr)
        await src.send(fr, bad=bad)
        await axis_tb.clocks(dut, 2 * len(fr) + 60)
    await axis_tb.clocks(dut, 500)
    got = [f for f, _ in sink.frames]
    assert len(got) == len(want), (len(got), len(want), kinds)
    for k, (g, w, q) in enumerate(zip(got, want, reqs)):
        assert g == w, (k, len(g), len(w), g[:48].hex(), w[:48].hex())
        scapy_check(g, q, ttl)
    assert ev.n["ev_request"] == ev.n["ev_reply"] == len(want) and ev.n["ev_busy"] == 0
    dut._log.info(f"echo: {N} frames, {len(want)} replies, kinds {kinds}, events {ev.n}")

    # a request that arrives while a reply is held by back-pressure is not answered
    sink.ready = 0.0
    n0 = len(sink.frames)
    r1 = model.request(inet.mac_b("02:bb:00:00:00:01"), OWN_MAC, inet.ip_b("192.168.10.9"), OWN_IP, 1, 1, b"abc")
    r2 = model.request(inet.mac_b("02:bb:00:00:00:02"), OWN_MAC, inet.ip_b("192.168.10.8"), OWN_IP, 2, 2, b"def")
    await src.send(r1)
    await axis_tb.clocks(dut, 20)
    await src.send(r2)
    await axis_tb.clocks(dut, 20)
    sink.ready = 1.0
    await axis_tb.clocks(dut, 300)
    assert [f for f, _ in sink.frames[n0:]] == [model.reply(r1, OWN_MAC, OWN_IP, ttl, buf)[0]]
    assert ev.n["ev_busy"] == 1
    # the declared latency: the request's last byte to the reply's first, output free
    lat = axis_tb.Latency(dut)
    await src.send(r2)
    await axis_tb.clocks(dut, 200)
    n = lat.clocks()
    assert n == LATENCY, n
    dut._log.info(f"latency: {n} clocks from the request's last byte to the reply's first")
    sink.stop()
