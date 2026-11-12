"""Small Internet-protocol helpers for the brief 63D models, written from the RFCs (plain Python, no scapy).

RFC 1071 (the Internet checksum), RFC 791 (IPv4), RFC 768 (UDP), RFC 826 (ARP), RFC 792 (ICMP), RFC 2236 (IGMPv2),
RFC 1112 section 6.4 (IPv4 multicast to Ethernet: 01-00-5E plus the low 23 bits).
"""
from __future__ import annotations

import struct


def csum(data: bytes) -> int:
    """RFC 1071: the ones' complement of the ones' complement sum of 16-bit words (odd length padded with zero)."""
    if len(data) % 2:
        data += b"\x00"
    s = sum(struct.unpack(f">{len(data) // 2}H", data))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return ~s & 0xFFFF


def ok(data: bytes) -> bool:
    """A block that carries its own checksum is intact when the sum over it all is 0xFFFF (csum 0)."""
    return csum(data) == 0


def ip_b(a: str | int) -> bytes:
    if isinstance(a, int):
        return a.to_bytes(4, "big")
    return bytes(int(x) for x in a.split("."))


def mac_b(a: str | int) -> bytes:
    if isinstance(a, int):
        return a.to_bytes(6, "big")
    return bytes.fromhex(a.replace(":", "").replace("-", ""))


def eth(da: bytes, sa: bytes, et: int, payload: bytes) -> bytes:
    return da + sa + struct.pack(">H", et) + payload


def ipv4(src: bytes, dst: bytes, proto: int, payload: bytes, ttl: int = 64, ident: int = 0, flags_frag: int = 0,
         options: bytes = b"", tos: int = 0) -> bytes:
    ihl = 5 + len(options) // 4
    h = struct.pack(">BBHHHBBH4s4s", 0x40 | ihl, tos, 4 * ihl + len(payload), ident, flags_frag, ttl, proto, 0, src,
                    dst) + options
    h = h[:10] + struct.pack(">H", csum(h)) + h[12:]
    return h + payload


def udp(src: bytes, dst: bytes, sport: int, dport: int, payload: bytes, checksum: bool = True) -> bytes:
    ln = 8 + len(payload)
    u = struct.pack(">HHHH", sport, dport, ln, 0) + payload
    if checksum:
        c = csum(src + dst + struct.pack(">BBH", 0, 17, ln) + u)
        u = u[:6] + struct.pack(">H", c or 0xFFFF) + u[8:]
    return u


def udp_ok(src: bytes, dst: bytes, u: bytes) -> bool:
    """A UDP datagram's checksum is right, or absent (0)."""
    if u[6:8] == b"\x00\x00":
        return True
    return ok(src + dst + struct.pack(">BBH", 0, 17, len(u)) + u)


def mcast_mac(ip: bytes) -> bytes:
    return bytes([0x01, 0x00, 0x5E, ip[1] & 0x7F, ip[2], ip[3]])


def arp(op: int, sha: bytes, spa: bytes, tha: bytes, tpa: bytes) -> bytes:
    return struct.pack(">HHBBH", 1, 0x0800, 6, 4, op) + sha + spa + tha + tpa
