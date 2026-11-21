"""The host-side Python of build rm_gp_itch (brief 127): frame builders, the replay image, the expected order frame, the plan as a script, and the order check on a synthetic capture."""
from __future__ import annotations

import struct
import zlib

from designs.b110_itch_ouch.model import gen, proto
from designs.b110_itch_ouch.model.ref import Cfg, Model
from designs.b96_kr260_10g.rm_gp_itch.host import itch_bench as B
from designs.b96_kr260_10g.rm_gp_itch.host import itch_host as H


def test_eth_ip_udp_headers_check_out() -> None:
    f = H.eth_ip_udp(b"hello", dst_mac=H.DEFAULTS["my_mac"], src_mac=H.DEFAULTS["venue_mac"], src_ip="192.168.58.15", dst_ip="192.168.58.10", sport=1, dport=5810)
    assert len(f) == 60 and f[12:14] == b"\x08\x00"
    assert H.csum16(f[14:34]) == 0                            # a valid IPv4 header sums to 0xFFFF: its checksum is 0
    assert struct.unpack(">H", f[38:40])[0] == 8 + 5          # the UDP length is what trims the padding
    big = H.eth_ip_udp(bytes(300), dst_mac=H.DEFAULTS["my_mac"], src_mac=H.DEFAULTS["venue_mac"], src_ip="1.2.3.4", dst_ip="5.6.7.8", sport=1, dport=2, udp_cksum=True)
    pseudo = bytes([1, 2, 3, 4, 5, 6, 7, 8, 0, 17]) + struct.pack(">H", 308)
    assert H.csum16(pseudo + big[34:342]) == 0


def test_multicast_mac() -> None:
    assert H.mcast_mac("233.54.12.1") == bytes([1, 0, 0x5E, 0x36, 12, 1])
    assert H.mcast_mac("239.255.255.255")[3] == 0x7F          # bit 23 of the address is dropped


def test_replay_image_layout_and_capacity() -> None:
    f1, f2 = bytes(range(60)), bytes(range(100))
    img = H.replay_image([(f1, 7), (f2, 0, True)], end_gap=33)
    assert img[0] == (7 << 16) | 60 and img[1 + 8] == (1 << 32) | 100 and img[-1] == 33 << 16
    assert len(img) == 1 + 8 + 1 + 13 + 1
    chunks = H.split_frames_for_memory([(bytes(1000), 0)] * 5)
    assert len(chunks) > 1 and all(len(H.replay_image(c)) <= 256 for c in chunks)


def test_xgmii_words_decode_with_the_reference_parser() -> None:
    from designs.b96_kr260_10g.model import pcs
    f = bytes(range(80))
    ok = [x for x in pcs.parse_xgmii(H.xgmii_words(f) + [H.IDLE_WORD] * 3) if "data" in x]
    bad = [x for x in pcs.parse_xgmii(H.xgmii_words(f, bad_fcs=True) + [H.IDLE_WORD] * 3) if "data" in x]
    assert ok[0]["data"] == f and ok[0]["fcs_ok"] and not bad[0]["fcs_ok"]


def test_order_frame_expectation_and_the_checksum_the_stand_in_lacks() -> None:
    cfg = Cfg()
    m = Model(cfg)
    g = gen.Gen(3, cfg)
    pre = proto.mold_packet(b"SESSION001", 1, g.preamble()[:3])
    add = proto.mold_packet(b"SESSION001", 4, [proto.itch_A(g.loc0, 1, 7, "B", 100, "AAA", gen.MID - 100)])
    sell = proto.mold_packet(b"SESSION001", 5, [proto.itch_A(g.loc0, 2, 8, "S", 100, "AAA", gen.MID - 50)])
    for p in (pre, add, sell):
        m.feed(p)
    assert len(m.orders) == 1
    kw = dict(my_mac=H.DEFAULTS["my_mac"], venue_mac=H.DEFAULTS["venue_mac"], my_ip="192.168.58.10", venue_ip="192.168.58.15", sport=5800, dport=5801, seq=1, ack=1)
    stub = H.tcp_stub_frame(m.orders[0]["frame"], **kw)
    real = H.tcp_frame_valid(m.orders[0]["frame"], **kw)
    assert len(stub) == 113 and stub[50:52] == b"\0\0" and real[50:52] != b"\0\0" and stub[:50] == real[:50] and stub[52:] == real[52:]
    assert H.csum16(stub[14:34]) == 0
    assert H.csum16(real[26:34] + struct.pack(">BBH", 0, 6, 79) + real[34:]) == 0          # the valid TCP checksum verifies over the pseudo-header
    assert not H.check_order_frame(stub, m.orders[0]["frame"], **kw)


def test_plan_script_and_decode() -> None:
    p = B.Plan()
    p.link().w(0x358, 5).d(100).poll(B.STAT["rp.stat"], 0x100, 0, 50).r(0x400, "a").r(0x404, "b")
    s = p.script()
    assert s.splitlines() == ["L", "W 358 00000005", "D 100", "D 50000", "R 400", "R 404", "E"]
    assert B.decode_log(p, "x\nRD 400 0000000a\nRD 404 000000ff\n") == {"a": 10, "b": 255}


def test_plan_runs_on_a_transport() -> None:
    class T:
        def __init__(self): self.w, self.v = [], {0x400: 7, 0x014: 0x203, B.STAT["rp.stat"]: 0}
        def wr(self, a, v): self.w.append((a, v))
        def rd(self, a): return self.v.get(a, 0)
    p = B.Plan()
    p.link().w(0x358, 5).poll(B.STAT["rp.stat"], 0x100, 0, 20).r(0x400, "a")
    t = T()
    assert p.run(t, sleep=lambda s: None) == {"a": 7} and t.w == [(0x358, 5)]


def test_counters_and_capture_check_on_a_synthetic_result() -> None:
    cfg = Cfg()
    m = Model(cfg)
    g = gen.Gen(3, cfg)
    for p in (proto.mold_packet(b"SESSION001", 1, g.preamble()[:3]), proto.mold_packet(b"SESSION001", 4, [proto.itch_A(g.loc0, 1, 7, "B", 100, "AAA", gen.MID - 100)]),
              proto.mold_packet(b"SESSION001", 5, [proto.itch_A(g.loc0, 2, 8, "S", 100, "AAA", gen.MID - 50)])):
        m.feed(p)
    res = {f"itch.{k}": v for k, v in m.cnt.items()}
    assert not B.counters_vs_model(res, m)
    res["itch.fire"] += 1
    assert B.counters_vs_model(res, m) == {"fire": (m.cnt["fire"] + 1, m.cnt["fire"])}
    kw = dict(my_mac=H.DEFAULTS["my_mac"], venue_mac=H.DEFAULTS["venue_mac"], my_ip="192.168.58.10", venue_ip="192.168.58.15", sport=5800, dport=5801, seq=1, ack=1)
    full = H.tcp_stub_frame(m.orders[0]["frame"], **kw)
    tail = (full[24:] + zlib.crc32(full).to_bytes(4, "little")).ljust(96, b"\0")
    r = {"us.cap_n": 1}
    for slot in range(8):
        meta = (1 << 17 | 1 << 16 | 117) if slot == 0 else 0
        r[f"cap{slot}.12.lo"], r[f"cap{slot}.12.hi"], r[f"cap{slot}.12.echo"] = meta, 0, (slot << 4) | 12
        for k in range(12):
            w = int.from_bytes(tail[8 * k:8 * k + 8], "little") if slot == 0 else 0
            r[f"cap{slot}.{k}.lo"], r[f"cap{slot}.{k}.hi"], r[f"cap{slot}.{k}.echo"] = w & 0xFFFFFFFF, w >> 32, (slot << 4) | k
    chk = B.order_frames_vs_model(r, m)
    assert chk["compared"] == 1 and not chk["problems"], chk
    r["cap0.5.lo"] ^= 1
    assert B.order_frames_vs_model(r, m)["problems"]
