"""Reference model of ipv4_udp_rx, written from RFC 791, RFC 768 and RFC 1071 and the entry's contract, not from the
RTL. rx() says what the block passes on for one frame: None (nothing) with the reason, or the payload with its
header fields and whether tuser marks it to be discarded."""
from __future__ import annotations

import struct

from flow.net import inet


def rx(frame: bytes, own_ip: bytes, ports: list, bad: bool = False, check_udp: bool = True, bcast: bool = True,
       mcast: bool = True):
    """ports: list of (port, enabled). Returns (out, reason): out = {payload, dest, src_ip, dst_ip, sport, dport,
    len, discard} or None."""
    if len(frame) < 34 or frame[12:14] != b"\x08\x00":
        return None, "not ipv4"
    vi = frame[14]
    hl = 4 * (vi & 0xF)
    if vi >> 4 != 4 or vi & 0xF < 5 or len(frame) < 14 + hl or not inet.ok(frame[14:14 + hl]):
        return None, "bad_ip"
    tl, ff = struct.unpack(">H", frame[16:18])[0], struct.unpack(">H", frame[20:22])[0]
    if tl < hl:
        return None, "bad_ip"
    src, dst, proto = frame[26:30], frame[30:34], frame[23]
    dst_ok = dst == own_ip or (bcast and dst == b"\xff" * 4) or (mcast and dst[0] >> 4 == 0xE)
    if ff & 0x3FFF:
        return None, "frag" if dst_ok else "not mine"
    if proto != 17 or not dst_ok:
        return None, "not mine"
    u0 = 14 + hl
    if len(frame) < u0 + 8:
        return None, "bad_udp"
    sport, dport, ulen, ucs = struct.unpack(">HHHH", frame[u0:u0 + 8])
    if ulen < 8 or ulen > tl - hl:
        return None, "bad_udp"
    dest = next((i for i, (p, en) in enumerate(ports) if en and p == dport), None)
    if dest is None:
        return None, "no_port"
    u = frame[u0:u0 + ulen]
    discard = bad or len(u) < ulen or (check_udp and ucs != 0 and not inet.udp_ok(src, dst, u))
    if ulen == 8:
        return None, "bad_udp" if discard else "empty"
    return {"payload": u[8:], "dest": dest, "src_ip": src, "dst_ip": dst, "sport": sport, "dport": dport,
            "len": ulen - 8, "discard": discard}, None
