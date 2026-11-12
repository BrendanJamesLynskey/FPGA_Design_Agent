"""Reference model of icmp_echo, written from RFC 792, RFC 791 and RFC 1122 3.2.2.6, not from the RTL. The reply's
checksums are computed from scratch here (the RTL updates them incrementally, RFC 1624), so the two methods check
each other."""
from __future__ import annotations

import struct

from flow.net import inet


def reply(frame: bytes, own_mac: bytes, own_ip: bytes, ttl: int = 64, buf: int = 2048, bad: bool = False):
    """(reply frame, None) or (None, reason)."""
    if len(frame) < 42 or frame[12:14] != b"\x08\x00":
        return None, "not ipv4"
    ip = frame[14:34]
    if ip[0] != 0x45 or ip[9] != 1 or ip[16:20] != own_ip:
        return None, "not icmp to us"
    tl = struct.unpack(">H", ip[2:4])[0]
    if frame[34] != 8:
        return None, "not echo request"
    if bad or frame[35] != 0 or struct.unpack(">H", ip[6:8])[0] & 0x3FFF or not inet.ok(ip) or tl < 28 or \
            len(frame) < 14 + tl or 14 + tl > buf or not inet.ok(frame[34:14 + tl]):
        return None, "bad"
    icmp = b"\x00" + frame[35:36] + b"\x00\x00" + frame[38:14 + tl]
    icmp = icmp[:2] + struct.pack(">H", inet.csum(icmp)) + icmp[4:]
    h = bytearray(ip)
    h[8] = ttl
    h[12:16], h[16:20] = ip[16:20], ip[12:16]
    h[10:12] = b"\x00\x00"
    h[10:12] = struct.pack(">H", inet.csum(bytes(h)))
    return frame[6:12] + own_mac + b"\x08\x00" + bytes(h) + icmp, None


def request(src_mac: bytes, own_mac: bytes, src_ip: bytes, own_ip: bytes, ident: int, seq: int, data: bytes,
            ttl: int = 64, ip_ident: int = 0, df: bool = False) -> bytes:
    icmp = struct.pack(">BBHHH", 8, 0, 0, ident, seq) + data
    icmp = icmp[:2] + struct.pack(">H", inet.csum(icmp)) + icmp[4:]
    return inet.eth(own_mac, src_mac, 0x0800, inet.ipv4(src_ip, own_ip, 1, icmp, ttl=ttl, ident=ip_ident,
                                                         flags_frag=0x4000 if df else 0))
