"""Reference model of ipv4_udp_tx, written from RFC 791, RFC 768 and RFC 1071 and the entry's contract, not from the
RTL: the frame for one payload (Ethernet II, IPv4 with IHL 5 and no fragmentation flags, UDP)."""
from __future__ import annotations

from flow.net import inet


def frame(payload: bytes, own_mac: bytes, own_ip: bytes, dst_mac: bytes, dst_ip: bytes, sport: int, dport: int,
          ident: int, ttl: int = 64, csum: bool = True) -> bytes:
    u = inet.udp(own_ip, dst_ip, sport, dport, payload, checksum=csum)
    return inet.eth(dst_mac, own_mac, 0x0800, inet.ipv4(own_ip, dst_ip, 17, u, ttl=ttl, ident=ident & 0xFFFF))
