"""Reference model of igmp_join's frames and rules, written from RFC 2236 (IGMPv2), RFC 2113 (Router Alert),
RFC 1112 6.4 (multicast MAC) and RFC 3376 7.2.1 (a version 2 host answers a version 3 query), not from the RTL."""
from __future__ import annotations

import struct

from flow.net import inet

ALL_ROUTERS = inet.ip_b("224.0.0.2")
ALL_HOSTS = inet.ip_b("224.0.0.1")
RA = b"\x94\x04\x00\x00"


def igmp(typ: int, mrt: int, group: bytes, extra: bytes = b"") -> bytes:
    m = struct.pack(">BBH4s", typ, mrt, 0, group) + extra
    return m[:2] + struct.pack(">H", inet.csum(m)) + m[4:]


def host_frame(own_mac: bytes, own_ip: bytes, group: bytes, leave: bool, ident: int) -> bytes:
    """A report (0x16, to the group) or a leave (0x17, to 224.0.0.2): TTL 1, Router Alert."""
    dst = ALL_ROUTERS if leave else group
    ip = inet.ipv4(own_ip, dst, 2, igmp(0x17 if leave else 0x16, 0, group), ttl=1, ident=ident, options=RA)
    return inet.eth(inet.mcast_mac(dst), own_mac, 0x0800, ip)


def query(router_mac: bytes, router_ip: bytes, group: bytes, mrt: int, v3: bool = False) -> bytes:
    extra = b"\x02\x7d\x00\x00" if v3 else b""          # S/QRV, QQIC, no sources
    dst = ALL_HOSTS if group == b"\x00" * 4 else group
    ip = inet.ipv4(router_ip, dst, 2, igmp(0x11, mrt, group, extra), ttl=1, options=RA)
    return inet.eth(inet.mcast_mac(dst), router_mac, 0x0800, ip)


def other_report(mac: bytes, ip: bytes, group: bytes) -> bytes:
    return inet.eth(inet.mcast_mac(group), mac, 0x0800, inet.ipv4(ip, group, 2, igmp(0x16, 0, group), ttl=1, options=RA))


def parse_host_frame(fr: bytes) -> dict:
    """Decode a frame the block sent, checking everything RFC 2236 asks of it."""
    assert fr[12:14] == b"\x08\x00" and fr[14] == 0x46 and inet.ok(fr[14:38]), fr.hex()
    assert fr[22] == 1 and fr[23] == 2 and fr[34:38] == RA
    tl = struct.unpack(">H", fr[16:18])[0]
    m = fr[38:14 + tl]
    assert len(m) == 8 and inet.ok(m)
    dst = fr[30:34]
    assert fr[:6] == inet.mcast_mac(dst)
    return {"type": m[0], "group": m[4:8], "dst": dst, "ident": struct.unpack(">H", fr[18:20])[0]}
