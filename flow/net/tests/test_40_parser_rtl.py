"""Brief 40, block 2: the streaming header parser (ip_lib/pkt_parser), bit-exact against flow/net/model.parse, which
is itself cross-checked against scapy's dissection of the same frames (an independent reading of the standards)."""
from __future__ import annotations

import ipaddress
import random

import pytest

from flow.net import model, pktio, sim, traffic

pytestmark = pytest.mark.skipif(not traffic.HAVE_SCAPY, reason="scapy not installed")

BLOCK = "pkt_parser"
TB = sim.IP / BLOCK / "tb" / "tb_pkt_parser.sv"


def srcs(rtl_dir=None):
    return sim.rtl(BLOCK, rtl_dir) + [TB]


def run(tmp, frames, sched="random", seed=1, rtl_dir=None, params=None, users=None):
    pktio.write_stream(tmp / "stim.txt", frames, users)
    ns = pktio.write_sched(tmp / "sched.txt", sched, seed=seed)
    sim.run(srcs(rtl_dir), "tb_pkt_parser", {"stim": tmp / "stim.txt", "sched": tmp / "sched.txt", "nsched": ns,
                                             "resp": tmp / "resp.txt"}, params=params, tag="parser")
    return pktio.read_resp(tmp / "resp.txt")


def check(r, frames, max_vlan=2, users=None):
    got = r["pkts"]["D"]
    assert [g[0] for g in got] == list(frames), "payload stream changed"
    if users:
        assert [g[1] for g in got] == users
    hdrs = [w[0] for _, w in r["words"]["H"]]
    want = [model.pack_hdr(model.parse(f, max_vlan)) for f in frames]
    assert len(hdrs) == len(want)
    bad = [i for i in range(len(want)) if hdrs[i] != want[i]]
    if bad:
        i = bad[0]
        g, w = model.unpack_hdr(hdrs[i]), model.unpack_hdr(want[i])
        diff = {k: (hex(g[k]), hex(w[k])) for k in g if g[k] != w[k]}
        raise AssertionError(f"{len(bad)} header mismatches; first frame {i} ({frames[i].hex()}): {diff}")


def test_model_agrees_with_scapy():
    """The golden model's fields match scapy's dissection on every well-formed frame of the mix."""
    from scapy.all import IP, TCP, UDP, Dot1Q, Dot1AD, Ether, IPv6
    n = 0
    for kind, fr in traffic.mix(21, 600):
        if kind in ("trunc", "badver", "badihl"):
            continue
        h = model.parse(fr)
        f = model.flags(h)
        p = Ether(fr)
        assert h["dmac"] == int(p.dst.replace(":", ""), 16) and h["smac"] == int(p.src.replace(":", ""), 16)
        tags = [l for l in p.layers() if l in (Dot1Q, Dot1AD)]
        assert f["vlan_n0"] + 2 * f["vlan_n1"] == len(tags)
        if IP in p:
            ip = p[IP]
            assert h["src"] == int.from_bytes(bytes(map(int, ip.src.split("."))), "big")
            assert h["ttl"] == ip.ttl and h["proto"] == ip.proto
            assert f["err_csum"] == int(kind == "badcsum")
            assert f["frag"] == int(bool(ip.flags.MF) or ip.frag != 0)
            l4 = (UDP if ip.proto == 17 else TCP) if ip.proto in (6, 17) and ip.frag == 0 else None
        elif IPv6 in p:
            ip = p[IPv6]
            assert h["dst"] == int.from_bytes(ipaddress.IPv6Address(ip.dst).packed, "big")
            assert h["ttl"] == ip.hlim
            l4 = (UDP if ip.nh == 17 else TCP) if ip.nh in (6, 17) else None
        else:
            l4 = None
        if l4 is not None:
            assert f["l4"] == 1 and h["sport"] == p[l4].sport and h["dport"] == p[l4].dport
        else:
            assert f["l4"] == 0
        n += 1
    assert n > 400


@pytest.mark.parametrize("sched,seed", [("continuous", 1), ("random", 2), ("random", 3)])
def test_parser_bit_exact(tmp_path, sched, seed):
    frames = [fr for _, fr in traffic.mix(100 + seed, 400, max_payload=80)]
    users = [int(i % 7 == 0) for i in range(len(frames))]
    r = run(tmp_path, frames, sched, seed, users=users)
    check(r, frames, users=users)


@pytest.mark.parametrize("max_vlan", [0, 1])
def test_parser_sweep_max_vlan(tmp_path, max_vlan):
    frames = [fr for _, fr in traffic.mix(300 + max_vlan, 200, kinds=["vlan1", "vlan2", "udp4", "trunc"],
                                          max_payload=40)]
    r = run(tmp_path, frames, "random", 5, params={"MAX_VLAN": max_vlan})
    check(r, frames, max_vlan)


def test_parser_guard():
    bad, out = sim.elaborate_fails(srcs(), "tb_pkt_parser", {"MAX_VLAN": 3})
    assert bad, out


def line_rate(tmp) -> dict:
    """Minimum frames back to back, continuous valid and ready: bytes a clock and header latency."""
    r0 = random.Random(9)
    frames = [traffic.frame("min", r0) for _ in range(300)]
    r = run(tmp, frames, "continuous", 1)
    check(r, frames)
    first = r["first"]["D"]
    cyc = (first[-1] - first[0]) / (len(first) - 1)
    h = [c for c, _ in r["words"]["H"]]
    lat_hdr = [hc - fc for hc, fc in zip(h, first)]
    return {"frames": len(frames), "clocks_per_60B_frame": cyc, "bytes_per_clock": 60 / cyc,
            "data_latency_clocks": first[0] - r["meta"]["first_in"],
            "hdr_after_first_byte_out_clocks": sorted(set(lat_hdr))}


def test_parser_line_rate(tmp_path):
    m = line_rate(tmp_path)
    assert m["clocks_per_60B_frame"] == 60.0


def test_parser_from_committed_pcap(tmp_path):
    """The committed sample capture (results/b40/pcap, written by flow/net/make_pcaps.py) through the parser."""
    frames = traffic.read_pcap(sim.ROOT / "results" / "b40" / "pcap" / "mix_seed101_in.pcap")
    assert len(frames) == 400
    check(run(tmp_path, frames, "random", 7), frames)
