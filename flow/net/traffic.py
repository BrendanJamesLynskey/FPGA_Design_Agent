"""Seeded test traffic for the packet-processing library (brief 40), built with scapy and written as pcap.

scapy (GPL-2.0-only) is a test-time tool here: it builds and dissects frames in the Python tests and is never
imported by, copied into, or shipped with any RTL or generated design. The library stays MIT. (Decision recorded in
`ip_lib/README.md` and the brief-40 report.)

Every frame is the Ethernet frame from the destination address to the end of the payload, without preamble or FCS
(the MAC adds and removes those). The mix covers minimum-size frames, one and two VLAN tags (0x8100 and 0x88A8
outer), IPv4 with and without options, IPv4 fragments, IPv6 with and without an extension header, UDP, TCP, ICMP,
ARP, and the malformed kinds: bad IPv4 header checksum, wrong IP version, IHL below 5, and frames truncated inside
a header.
"""
from __future__ import annotations

import random

try:
    from scapy.all import (ARP, ICMP, IP, TCP, UDP, Dot1AD, Dot1Q, Ether, IPOption_NOP, IPOption_Router_Alert,
                           IPv6, IPv6ExtHdrHopByHop, Raw, wrpcap, rdpcap)
    HAVE_SCAPY = True
except ImportError:          # the RTL tests skip when scapy is missing
    HAVE_SCAPY = False

KINDS = ["udp4", "tcp4", "opt4", "frag4", "udp6", "tcp6", "ext6", "icmp4", "arp", "vlan1", "vlan2",
         "badcsum", "badver", "badihl", "trunc", "min"]


def _mac(r: random.Random, pool=None) -> str:
    if pool:
        return r.choice(pool)
    b = [r.randrange(256) for _ in range(6)]
    b[0] &= 0xFE                                 # unicast
    return ":".join(f"{x:02x}" for x in b)


def _ip4(r: random.Random) -> str:
    return ".".join(str(r.randrange(1, 255)) for _ in range(4))


def _ip6(r: random.Random) -> str:
    return ":".join(f"{r.randrange(65536):x}" for _ in range(8))


def _payload(r: random.Random, lo: int, hi: int) -> bytes:
    return bytes(r.randrange(256) for _ in range(r.randint(lo, hi)))


def frame(kind: str, r: random.Random, max_payload: int = 200, macs=None) -> bytes:
    """One frame of the given kind (bytes, destination address .. payload)."""
    eth = Ether(dst=_mac(r, macs), src=_mac(r, macs))
    pl = _payload(r, 0, max_payload)
    l4 = UDP(sport=r.randrange(65536), dport=r.randrange(65536)) if r.random() < 0.5 else \
        TCP(sport=r.randrange(65536), dport=r.randrange(65536), flags="PA", seq=r.randrange(1 << 32))
    if kind == "udp4":
        p = eth / IP(src=_ip4(r), dst=_ip4(r), ttl=r.randint(1, 255)) / UDP(sport=r.randrange(65536),
                                                                           dport=r.randrange(65536)) / Raw(pl)
    elif kind == "tcp4":
        p = eth / IP(src=_ip4(r), dst=_ip4(r), ttl=r.randint(1, 255)) / TCP(sport=r.randrange(65536),
                                                                           dport=r.randrange(65536)) / Raw(pl)
    elif kind == "opt4":
        opts = [IPOption_Router_Alert()] + [IPOption_NOP()] * r.choice([0, 4, 8, 20])
        p = eth / IP(src=_ip4(r), dst=_ip4(r), options=opts) / l4 / Raw(pl)
    elif kind == "frag4":
        p = eth / IP(src=_ip4(r), dst=_ip4(r), flags=r.choice(["MF", 0]), frag=r.choice([0, 1, 185])) / l4 / Raw(pl)
    elif kind == "udp6":
        p = eth / IPv6(src=_ip6(r), dst=_ip6(r), hlim=r.randint(1, 255)) / UDP(sport=r.randrange(65536),
                                                                              dport=r.randrange(65536)) / Raw(pl)
    elif kind == "tcp6":
        p = eth / IPv6(src=_ip6(r), dst=_ip6(r)) / TCP(sport=r.randrange(65536), dport=r.randrange(65536)) / Raw(pl)
    elif kind == "ext6":
        p = eth / IPv6(src=_ip6(r), dst=_ip6(r)) / IPv6ExtHdrHopByHop() / l4 / Raw(pl)
    elif kind == "icmp4":
        p = eth / IP(src=_ip4(r), dst=_ip4(r)) / ICMP() / Raw(pl)
    elif kind == "arp":
        p = eth / ARP(psrc=_ip4(r), pdst=_ip4(r))
    elif kind == "vlan1":
        p = eth / Dot1Q(vlan=r.randrange(4096), prio=r.randrange(8)) / IP(src=_ip4(r), dst=_ip4(r)) / l4 / Raw(pl)
    elif kind == "vlan2":
        p = (eth / Dot1AD(vlan=r.randrange(4096)) / Dot1Q(vlan=r.randrange(4096)) /
             (IP(src=_ip4(r), dst=_ip4(r)) if r.random() < 0.6 else IPv6(src=_ip6(r), dst=_ip6(r))) / l4 / Raw(pl))
    elif kind == "badcsum":
        ip = IP(src=_ip4(r), dst=_ip4(r)) / l4 / Raw(pl)
        ip = IP(bytes(ip))
        ip.chksum = (ip.chksum + 1 + r.randrange(0xFFFE)) & 0xFFFF
        p = eth / ip
    elif kind == "badver":
        b = bytearray(bytes(IP(src=_ip4(r), dst=_ip4(r)) / l4 / Raw(pl)))
        b[0] = (r.choice([5, 6, 7, 15]) << 4) | (b[0] & 0x0F)
        p = eth / Raw(bytes(b))
        p[Ether].type = 0x0800
    elif kind == "badihl":
        b = bytearray(bytes(IP(src=_ip4(r), dst=_ip4(r)) / l4 / Raw(pl)))
        b[0] = 0x40 | r.randrange(5)
        p = eth / Raw(bytes(b))
        p[Ether].type = 0x0800
    elif kind == "trunc":
        full = bytes(frame(r.choice(["udp4", "tcp4", "opt4", "udp6", "vlan1", "vlan2"]), r, max_payload, macs))
        return full[:r.randint(6, min(len(full), 70))]
    elif kind == "min":
        p = eth / IP(src=_ip4(r), dst=_ip4(r)) / UDP(sport=r.randrange(65536), dport=r.randrange(65536))
        b = bytes(p)
        return b + bytes(max(0, 60 - len(b)))
    else:
        raise ValueError(kind)
    b = bytes(p)
    if len(b) < 60 and kind != "trunc":
        b = b + bytes(60 - len(b))               # the MAC would pad; generate padded frames
    return b


def mix(seed: int, n: int, kinds=None, max_payload: int = 200, macs=None) -> list[tuple[str, bytes]]:
    r = random.Random(seed)
    kinds = kinds or KINDS
    return [(k, frame(k, r, max_payload, macs)) for k in (r.choice(kinds) for _ in range(n))]


def write_pcap(path, frames) -> None:
    """Classic pcap (LINKTYPE_ETHERNET), written directly so that truncated frames (shorter than an Ethernet header)
    are kept exactly. `frames`: bytes, or (kind, bytes) pairs."""
    import struct
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for i, fr in enumerate(frames):
            b = fr[1] if isinstance(fr, tuple) else fr
            f.write(struct.pack("<IIII", i // 1000, (i % 1000) * 1000, len(b), len(b)))
            f.write(b)


def read_pcap(path) -> list[bytes]:
    import struct
    data = open(path, "rb").read()
    out, o = [], 24
    while o + 16 <= len(data):
        n = struct.unpack_from("<IIII", data, o)[2]
        out.append(data[o + 16:o + 16 + n])
        o += 16 + n
    return out
