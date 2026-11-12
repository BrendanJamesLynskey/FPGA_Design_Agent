"""cocotb bench for ip_lib/ipv4_udp_rx against ip_lib/ipv4_udp_rx/model.py (RFC 791/768/1071), frames built by
flow/net/inet.py and cross-checked by scapy (test time only). Datagrams to us, to broadcast, to multicast and to
others; enabled, disabled and unknown ports; right, wrong and absent UDP checksums; IP options, fragments, other
protocols, bad header checksums, UDP lengths shorter than the IP payload, Ethernet padding, bad and truncated frames,
empty payloads; random input gaps and output back-pressure. Environment: URX_SEED, URX_N."""
from __future__ import annotations

import os
import random
import struct

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge

from flow.net import inet
from flow.net.tests import axis_tb
from ip_lib.ipv4_udp_rx import model

SEED = int(os.environ.get("URX_SEED", "1"))
N = int(os.environ.get("URX_N", "250"))
OWN_MAC = inet.mac_b("02:00:00:00:00:01")
OWN_IP = inet.ip_b("192.168.10.2")
SIDE = ("m_axis_tdest", "m_src_ip", "m_dst_ip", "m_src_port", "m_dst_port", "m_len")
EVS = ("ev_ok", "ev_bad_ip", "ev_bad_udp", "ev_no_port", "ev_frag", "ev_empty")
try:
    from scapy.layers.inet import IP, UDP
    from scapy.layers.l2 import Ether
    HAVE_SCAPY = True
except ImportError:
    HAVE_SCAPY = False


def make(rng: random.Random, ports):
    src = inet.ip_b(f"192.168.10.{rng.randrange(3, 250)}")
    dst = rng.choice([OWN_IP] * 6 + [b"\xff" * 4, inet.ip_b("239.1.2.3"), inet.ip_b("192.168.10.77")])
    dport = rng.choice([p for p, _ in ports] * 3 + [rng.randrange(65536)])
    n = rng.choice([0, 1, 2, 5, 17, 18, 64, 300, rng.randrange(1473)])
    pay = bytes(rng.randrange(256) for _ in range(n))
    kind = rng.choice(["ok"] * 10 + ["nocs", "badcs", "opts", "frag", "proto", "ipcs", "short_ulen", "bad", "trunc",
                                     "big_ulen", "tiny_ulen"])
    u = bytearray(inet.udp(src, dst, rng.randrange(1, 65536), dport, pay, checksum=kind != "nocs"))
    if kind == "badcs":
        u[6] ^= 0x01
        if u[6:8] == b"\x00\x00":
            u[7] = 1
    extra = b""
    if kind == "short_ulen":                      # the IP payload carries bytes after the datagram
        extra = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 9)))
    if kind == "big_ulen":
        u[4:6] = struct.pack(">H", len(u) + 4)
    if kind == "tiny_ulen":
        u[4:6] = struct.pack(">H", rng.randrange(8))
    ip = inet.ipv4(src, dst, 6 if kind == "proto" else 17, bytes(u) + extra, ident=rng.randrange(65536),
                   flags_frag=0x2000 if kind == "frag" else 0x4000 * rng.randrange(2),
                   options=b"\x01\x01\x01\x00\x01\x01\x01\x00" if kind == "opts" else b"")
    ip = bytearray(ip)
    if kind == "ipcs":
        ip[10] ^= 0x40
    da = inet.mcast_mac(dst) if dst[0] >> 4 == 0xE else OWN_MAC
    fr = inet.eth(da, inet.mac_b("02:cc:00:00:00:05"), 0x0800, bytes(ip))
    if kind == "trunc":
        fr = fr[:len(fr) - 1 - rng.randrange(min(6, len(fr) - 36))]
    if len(fr) < 60:                              # Ethernet padding: zeros or (allowed) anything
        fr += bytes(rng.randrange(256) if rng.random() < 0.5 else 0 for _ in range(60 - len(fr)))
    return fr, kind == "bad", kind


@cocotb.test()
async def udp_rx(dut):
    np_, chk = int(dut.N_PORTS.value), int(dut.CHECK_UDP.value)
    bc, mc = int(dut.ACCEPT_BCAST.value), int(dut.ACCEPT_MCAST.value)
    rng = random.Random(SEED + 10 * np_ + chk)
    ports = [(rng.randrange(1, 65536), rng.random() < 0.8) for _ in range(np_)]
    ports[0] = (ports[0][0], True)
    if np_ > 2:
        ports[-1] = (ports[1][0], True)           # a duplicate: the lowest index must win
    dut.own_ip.value = int.from_bytes(OWN_IP, "big")
    dut.ports.value = sum(p << (16 * i) for i, (p, _) in enumerate(ports))
    dut.port_en.value = sum(int(e) << i for i, (_, e) in enumerate(ports))
    await axis_tb.start(dut)
    src = axis_tb.Source(dut, rng, gap=0.15)
    sink = axis_tb.Sink(dut, rng, ready=0.75, user=True, side=SIDE)
    n_ev = {k: 0 for k in EVS}

    async def count():
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            for k in EVS:
                n_ev[k] += int(getattr(dut, k).value)
    cocotb.start_soon(count())
    want, kinds, reasons = [], {}, {}
    for _ in range(N):
        fr, bad, kind = make(rng, ports)
        if HAVE_SCAPY and kind == "ok":           # scapy recomputes the UDP checksum of our frame from scratch
            p = Ether(fr)
            c = p[UDP].chksum
            del p[UDP].chksum
            assert Ether(bytes(p))[UDP].chksum == c, "the bench's own UDP checksum is wrong"
        out, why = model.rx(fr, OWN_IP, ports, bad, bool(chk), bool(bc), bool(mc))
        kinds[kind] = kinds.get(kind, 0) + 1
        reasons[why or ("discard" if out["discard"] else "ok")] = reasons.get(why or ("discard" if out["discard"] else "ok"), 0) + 1
        if out:
            want.append(out)
        await src.send(fr, bad=bad)
    await axis_tb.clocks(dut, 3000)
    sink.stop()
    got = sink.frames
    assert len(got) == len(want), (len(got), len(want), reasons)
    for k, ((g, info), w) in enumerate(zip(got, want)):
        assert g == w["payload"], (k, g.hex(), w["payload"].hex())
        assert info["tuser"] == int(w["discard"]), (k, w)
        side = (w["dest"], int.from_bytes(w["src_ip"], "big"), int.from_bytes(w["dst_ip"], "big"), w["sport"],
                w["dport"], w["len"])
        assert info["side"] == side, (k, info["side"], side)
    assert n_ev["ev_ok"] == reasons.get("ok", 0), (n_ev, reasons)
    assert n_ev["ev_no_port"] == reasons.get("no_port", 0), (n_ev, reasons)
    assert n_ev["ev_frag"] == reasons.get("frag", 0), (n_ev, reasons)
    assert n_ev["ev_empty"] == reasons.get("empty", 0), (n_ev, reasons)
    assert n_ev["ev_bad_udp"] == reasons.get("discard", 0) + reasons.get("bad_udp", 0), (n_ev, reasons)
    assert n_ev["ev_bad_ip"] == reasons.get("bad_ip", 0), (n_ev, reasons)
    dut._log.info(f"udp_rx: {N} frames, {len(want)} payloads out, kinds {kinds}, reasons {reasons}, events {n_ev}")
