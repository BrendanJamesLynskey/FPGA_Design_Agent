"""Bench Feed v1: our own mock market-data and order format (docs/bench_feed_v1.md), and the Ethernet/IPv4/UDP/ARP
frames that carry it. Plain Python, written from the format document and the standards, not from the RTL.

Shared by the reference model, the cocotb tests and the mock venue (host/mock_venue.py)."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

MAGIC = 0x4246            # "BF"
VERSION = 1
ADD, MODIFY, CANCEL, TRADE = 1, 2, 3, 4
NEW_ORDER, CANCEL_ORDER = 0x10, 0x11
BID, ASK = 0, 1
BUY, SELL = 0, 1
MSG_LEN = 16
HDR_LEN = 8
MAX_MSGS = 91             # 20 + 8 + 8 + 16*91 = 1492 bytes of IP datagram
ETH_IPV4, ETH_ARP = 0x0800, 0x0806
PREAMBLE = bytes([0x55] * 7 + [0xD5])

# locally administered example addresses (bit 1 of the first octet set): never a real interface's
BOARD_MAC = 0x02_00_00_00_58_0A
VENUE_MAC = 0x02_00_00_00_58_0F
GEN_MAC = 0x02_00_00_00_58_0B
BOARD_IP = 0xC0A83A0A     # 192.168.58.10
VENUE_IP = 0xC0A83A0F     # 192.168.58.15
GEN_IP = 0xC0A83A0B       # 192.168.58.11
BOARD_PORT, VENUE_PORT, GEN_PORT = 5800, 5801, 5802


@dataclass
class Msg:
    type: int
    side: int
    inst: int
    price: int            # hundredths
    size: int
    ref: int = 0

    def pack(self) -> bytes:
        return struct.pack(">BBHIII", self.type, self.side, self.inst, self.price, self.size, self.ref)

    @classmethod
    def unpack(cls, b: bytes) -> "Msg":
        t, s, i, p, z, r = struct.unpack(">BBHIII", b[:16])
        return cls(t, s, i, p, z, r)


def packet(seq: int, msgs: list[Msg], magic: int = MAGIC, version: int = VERSION, count: int | None = None) -> bytes:
    """A Bench Feed v1 UDP payload: header (magic, version, count, sequence of the first message) and messages."""
    n = len(msgs) if count is None else count
    return struct.pack(">HBBI", magic, version, n, seq) + b"".join(m.pack() for m in msgs)


def mac_bytes(m: int) -> bytes:
    return m.to_bytes(6, "big")


def ip_checksum(hdr: bytes) -> int:
    s = sum(struct.unpack(f">{len(hdr) // 2}H", hdr))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def ipv4_udp(src_ip: int, dst_ip: int, sport: int, dport: int, payload: bytes, *, ttl: int = 64, ident: int = 0,
             flags_frag: int = 0x4000, proto: int = 17, ihl_byte: int = 0x45, bad_csum: bool = False,
             udp_len: int | None = None) -> bytes:
    ulen = 8 + len(payload) if udp_len is None else udp_len
    udp = struct.pack(">HHHH", sport, dport, ulen, 0) + payload
    tlen = 20 + len(udp)
    hdr = struct.pack(">BBHHHBBHII", ihl_byte, 0, tlen, ident, flags_frag, ttl, proto, 0, src_ip, dst_ip)
    c = ip_checksum(hdr) ^ (0x0001 if bad_csum else 0)
    return hdr[:10] + struct.pack(">H", c) + hdr[12:] + udp


def ethernet(dst: int, src: int, ethertype: int, body: bytes, pad: bool = True) -> bytes:
    f = mac_bytes(dst) + mac_bytes(src) + struct.pack(">H", ethertype) + body
    if pad and len(f) < 60:
        f += bytes(60 - len(f))
    return f


def fcs(frame: bytes) -> bytes:
    return struct.pack("<I", zlib.crc32(frame) & 0xFFFFFFFF)


def with_fcs(frame: bytes, bad: bool = False) -> bytes:
    f = fcs(frame)
    if bad:
        f = bytes([f[0] ^ 0x01]) + f[1:]
    return frame + f


def feed_frame(seq: int, msgs: list[Msg], *, dst_mac: int = BOARD_MAC, src_mac: int = VENUE_MAC,
               src_ip: int = VENUE_IP, dst_ip: int = BOARD_IP, sport: int = VENUE_PORT, dport: int = BOARD_PORT,
               **kw) -> bytes:
    """A feed frame without its FCS."""
    pk = {k: kw.pop(k) for k in ("magic", "version", "count") if k in kw}
    return ethernet(dst_mac, src_mac, ETH_IPV4, ipv4_udp(src_ip, dst_ip, sport, dport, packet(seq, msgs, **pk), **kw))


def arp_request(sha: int, spa: int, tpa: int, oper: int = 1, dst: int = 0xFFFFFFFFFFFF) -> bytes:
    body = struct.pack(">HHBBH", 1, 0x0800, 6, 4, oper) + mac_bytes(sha) + struct.pack(">I", spa) + bytes(6) + \
        struct.pack(">I", tpa)
    return ethernet(dst, sha, ETH_ARP, body)


def arp_reply(our_mac: int, our_ip: int, to_mac: int, to_ip: int) -> bytes:
    body = struct.pack(">HHBBH", 1, 0x0800, 6, 4, 2) + mac_bytes(our_mac) + struct.pack(">I", our_ip) + \
        mac_bytes(to_mac) + struct.pack(">I", to_ip)
    return ethernet(to_mac, our_mac, ETH_ARP, body)


@dataclass
class Order:
    type: int             # NEW_ORDER or CANCEL_ORDER
    side: int
    inst: int
    price: int
    qty: int
    order_id: int
    seq: int = 0


def order_frame(o: Order, *, src_mac: int = BOARD_MAC, dst_mac: int = VENUE_MAC, src_ip: int = BOARD_IP,
                dst_ip: int = VENUE_IP, sport: int = BOARD_PORT, dport: int = VENUE_PORT) -> bytes:
    """The response frame the board sends for an order or a cancel (no FCS): one-message Bench Feed v1 packet."""
    body = struct.pack(">HBBI", MAGIC, VERSION, 1, o.seq) + struct.pack(">BBHIII", o.type, o.side, o.inst, o.price,
                                                                         o.qty, o.order_id)
    return ethernet(dst_mac, src_mac, ETH_IPV4, ipv4_udp(src_ip, dst_ip, sport, dport, body, ident=o.seq & 0xFFFF))


def parse_order(frame: bytes) -> Order | None:
    """An order or cancel from a response frame (no FCS), or None if it is not one."""
    if len(frame) < 66 or frame[12:14] != b"\x08\x00" or frame[23] != 17:
        return None
    pl = frame[42:66]
    magic, ver, cnt, seq = struct.unpack(">HBBI", pl[:8])
    if magic != MAGIC or ver != VERSION or cnt != 1:
        return None
    t, s, i, p, q, oid = struct.unpack(">BBHIII", pl[8:24])
    if t not in (NEW_ORDER, CANCEL_ORDER):
        return None
    return Order(t, s, i, p, q, oid, seq)


def split_wire(stream: list[tuple[int, int]]) -> list[bytes]:
    """GMII (tx_en, byte) samples -> the frames on the wire, preamble and SFD included."""
    frames, cur = [], None
    for en, b in stream:
        if en:
            cur = bytearray() if cur is None else cur
            cur.append(b)
        elif cur is not None:
            frames.append(bytes(cur))
            cur = None
    if cur is not None:
        frames.append(bytes(cur))
    return frames


def check_wire_frame(w: bytes) -> tuple[bytes, bool]:
    """(frame without preamble and FCS, FCS good) for a frame as sent on the wire."""
    if w[:8] != PREAMBLE:
        raise ValueError(f"bad preamble/SFD {w[:8].hex()}")
    body, f = w[8:-4], w[-4:]
    return body, fcs(body) == f
