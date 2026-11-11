"""Brief 40, block 4: header rewrite with incremental checksum update (ip_lib/pkt_rewrite), bit-exact against
model.rewrite; the model's checksums are checked independently by scapy recomputing them from scratch."""
from __future__ import annotations

import random

import pytest

from flow.net import model, pktio, sim, traffic

pytestmark = pytest.mark.skipif(not traffic.HAVE_SCAPY, reason="scapy not installed")

BLOCK = "pkt_rewrite"
TB = sim.IP / BLOCK / "tb" / "tb_pkt_rewrite.sv"


def srcs(rtl_dir=None):
    return sim.rtl(BLOCK, rtl_dir) + [TB]


def rand_act(r: random.Random) -> int:
    kw = {"port": r.randrange(16), "queue": r.randrange(8)}
    if r.random() < 0.05:
        kw["drop"] = 1
    for f, w in (("set_dmac", "dmac"), ("set_smac", "smac")):
        if r.random() < 0.5:
            kw[f], kw[w] = 1, r.getrandbits(48)
    if r.random() < 0.5:
        kw["dec_ttl"] = 1
    if r.random() < 0.3:
        kw["set_vid"], kw["vid"] = 1, r.getrandbits(12)
    u = r.random()
    if u < 0.15:
        kw["push_vlan"] = 1
    elif u < 0.3:
        kw["pop_vlan"] = 1
    elif u < 0.35:
        kw["push_vlan"] = kw["pop_vlan"] = 1
    if r.random() < 0.5:
        kw["set_dip"], kw["dip"] = 1, r.getrandbits(32)
    return model.pack_act(**kw)


def case(seed, n=400):
    r = random.Random(seed)
    frames = [fr for _, fr in traffic.mix(seed, n, max_payload=60)]
    for i in range(0, n, 37):                      # some UDP checksums of zero (no checksum)
        h = model.parse(frames[i])
        if model.flags(h)["udp"] and model.flags(h)["l4"] and h["l4off"] + 8 <= len(frames[i]):
            b = bytearray(frames[i]); b[h["l4off"] + 6] = b[h["l4off"] + 7] = 0; frames[i] = bytes(b)
    hdrs = [model.parse(f) for f in frames]
    acts = [rand_act(r) for _ in frames]
    return frames, hdrs, acts


def run(tmp, frames, hdrs, acts, sched="random", seed=1, rtl_dir=None):
    pktio.write_stream(tmp / "stim.txt", frames)
    with open(tmp / "meta.txt", "w") as f:
        for h, a in zip(hdrs, acts):
            f.write(f"{model.pack_hdr(h):0120x} {a:040x}\n")
    ns = pktio.write_sched(tmp / "sched.txt", sched, seed=seed)
    sim.run(srcs(rtl_dir), "tb_pkt_rewrite", {"stim": tmp / "stim.txt", "meta": tmp / "meta.txt",
                                              "sched": tmp / "sched.txt", "nsched": ns, "resp": tmp / "resp.txt"},
            tag="rewrite")
    return pktio.read_resp(tmp / "resp.txt")


def expected(frames, hdrs, acts):
    out, nttl = [], 0
    for f, h, a in zip(frames, hdrs, acts):
        o, dest, ttl = model.rewrite(f, h, a)
        nttl += ttl
        if o is not None:
            out.append((o, 0, dest))
    return out, nttl


@pytest.mark.parametrize("sched,seed", [("continuous", 1), ("random", 2), ("random", 3)])
def test_rewrite_bit_exact(tmp_path, sched, seed):
    frames, hdrs, acts = case(40 + seed)
    r = run(tmp_path, frames, hdrs, acts, sched, seed)
    want, nttl = expected(frames, hdrs, acts)
    got = r["pkts"]["D"]
    assert len(got) == len(want)
    bad = [i for i in range(len(want)) if got[i] != want[i]]
    assert not bad, f"{len(bad)} mismatches, first {bad[0]}: got {got[bad[0]]} want {want[bad[0]]}"
    assert r["meta"]["ttl_drops"] == nttl


def test_model_checksums_match_scapy():
    """Independent check of RFC 1624 in the model: for intact IPv4 packets the incrementally updated IP and L4
    checksums equal scapy's full recomputation."""
    from scapy.all import IP, TCP, UDP, Ether
    frames, hdrs, acts = case(77, 600)
    n = n4 = 0
    for f, h, a in zip(frames, hdrs, acts):
        fl = model.flags(h)
        if not (fl["ipv4"] and not fl["trunc"] and not fl["err_csum"] and not fl["err_ihl"] and not fl["err_ver"]):
            continue
        o, _, _ = model.rewrite(f, h, a)
        if o is None:
            continue
        p = Ether(o)
        ip = p[IP]
        c = ip.chksum
        del ip.chksum
        assert IP(bytes(ip))[IP].chksum == c
        for L in (UDP, TCP):
            if fl["l4"] and L in p and not fl["frag"]:
                orig = Ether(f)[L].chksum
                q = p[L]
                c4 = q.chksum
                if L is UDP and orig == 0:
                    assert c4 == 0
                    continue
                q0 = Ether(f)
                del q0[L].chksum
                if Ether(bytes(q0))[L].chksum != orig:
                    continue                       # the original was not valid (a cut payload): nothing to keep
                del q.chksum
                assert Ether(bytes(p))[L].chksum == c4
                n4 += 1
        n += 1
    assert n > 150 and n4 > 50


def line_rate(tmp) -> dict:
    r = random.Random(3)
    frames = [traffic.frame("min", r) for _ in range(200)]
    hdrs = [model.parse(f) for f in frames]
    acts = [model.pack_act(port=1, set_dmac=1, dmac=0x020000000001, dec_ttl=1) for _ in frames]
    for h in hdrs:
        h["ttl"] = max(h["ttl"], 2)
    frames = [f[:22] + bytes([max(f[22], 2)]) + f[23:] for f in frames]
    hdrs = [model.parse(f) for f in frames]
    res = run(tmp, frames, hdrs, acts, "continuous", 1)
    want, _ = expected(frames, hdrs, acts)
    assert res["pkts"]["D"] == want
    first = res["first"]["D"]
    return {"clocks_per_60B_frame": (first[-1] - first[0]) / (len(first) - 1),
            "latency_clocks": first[0] - res["meta"]["first_in"]}


def test_rewrite_line_rate(tmp_path):
    m = line_rate(tmp_path)
    assert m["clocks_per_60B_frame"] == 60.0


def test_rewrite_matches_committed_expected_pcap(tmp_path):
    """The committed input capture through pkt_rewrite gives the committed expected capture, byte for byte."""
    d = sim.ROOT / "results" / "b40" / "pcap"
    frames = traffic.read_pcap(d / "rewrite_seed41_in.pcap")
    f2, hdrs, acts = case(41)
    assert frames == f2
    r = run(tmp_path, frames, hdrs, acts, "random", 4)
    assert [g[0] for g in r["pkts"]["D"]] == traffic.read_pcap(d / "rewrite_seed41_expected.pcap")
