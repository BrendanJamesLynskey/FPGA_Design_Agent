"""Reference for the TCP fast path (brief 119): Ethernet/IPv4/TCP segments built and checked independently of the RTL.

The checksums are the Internet checksum of RFC 1071 (the sum of 16-bit big-endian words with end-around carry, complemented), written here from the RFC
and cross-checked in tests/test_b119_model.py against vectors that did not come from this repository (RFC 1071's own example, a published IPv4 header).
`FastModel` is the untimed model of the block's register file and decisions; the bench compares every segment and counter with it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PAYLEN = 59            # one SoupBinTCP Unsequenced Data packet carrying an OUCH 5.0 Enter Order (brief 110)
HDRLEN = 54            # Ethernet 14 + IPv4 20 + TCP 20
FRAMELEN = HDRLEN + PAYLEN
M32 = 0xFFFFFFFF

REFUSE_NOT_ARMED, REFUSE_STALE, REFUSE_WINDOW, REFUSE_MSS, REFUSE_BUSY = 1, 2, 3, 4, 5


def words_sum(data: bytes, init: int = 0) -> int:
    """Exact sum of the 16-bit big-endian words of data (an odd last byte is the high byte of a word), plus init."""
    if len(data) % 2:
        data += b"\0"
    return init + sum((data[i] << 8) | data[i + 1] for i in range(0, len(data), 2))


def fold(x: int) -> int:
    while x >> 16:
        x = (x & 0xFFFF) + (x >> 16)
    return x


def checksum(data: bytes, init: int = 0) -> int:
    """RFC 1071: the complement of the folded sum."""
    return (~fold(words_sum(data, init))) & 0xFFFF


def ip_bytes(a) -> bytes:
    return a if isinstance(a, bytes) else int(a).to_bytes(4, "big")


@dataclass
class Conn:
    """The static part of a connection, as software writes it to the block."""
    dmac: bytes = bytes.fromhex("02aabbccdd01")
    smac: bytes = bytes.fromhex("02aabbccdd02")
    sip: int = 0x0A000002
    dip: int = 0x0A000001
    sport: int = 40001
    dport: int = 5001
    ttl: int = 64
    mss: int = 1460


def ip_header(c: Conn, ident: int, total_len: int, flags_frag: int = 0x4000) -> bytes:
    h = bytes([0x45, 0]) + total_len.to_bytes(2, "big") + ident.to_bytes(2, "big") + flags_frag.to_bytes(2, "big") + bytes([c.ttl, 6, 0, 0]) \
        + ip_bytes(c.sip) + ip_bytes(c.dip)
    return h[:10] + checksum(h).to_bytes(2, "big") + h[12:]


def tcp_segment(src_ip: int, dst_ip: int, sport: int, dport: int, seq: int, ack: int, flags: int, win: int, payload: bytes, options: bytes = b"") -> bytes:
    """A TCP segment (header, options, payload) with its checksum over the pseudo-header."""
    off = (20 + len(options)) // 4
    h = sport.to_bytes(2, "big") + dport.to_bytes(2, "big") + (seq & M32).to_bytes(4, "big") + (ack & M32).to_bytes(4, "big") \
        + bytes([off << 4, flags]) + win.to_bytes(2, "big") + b"\0\0" + b"\0\0" + options
    seg = h + payload
    pseudo = ip_bytes(src_ip) + ip_bytes(dst_ip) + bytes([0, 6]) + len(seg).to_bytes(2, "big")
    cs = checksum(pseudo + seg)
    return seg[:16] + cs.to_bytes(2, "big") + seg[18:]


def frame(c: Conn, seq: int, ack: int, win: int, ident: int, payload: bytes, flags: int = 0x18, options: bytes = b"", src_to_dst: bool = True) -> bytes:
    """A complete Ethernet frame (no FCS). src_to_dst False builds the reverse direction (peer to us)."""
    if src_to_dst:
        dmac, smac, sip, dip, sp, dp = c.dmac, c.smac, c.sip, c.dip, c.sport, c.dport
    else:
        dmac, smac, sip, dip, sp, dp = c.smac, c.dmac, c.dip, c.sip, c.dport, c.sport
    seg = tcp_segment(sip, dip, sp, dp, seq, ack, flags, win, payload, options)
    cc = Conn(dmac, smac, sip, dip, sp, dp, c.ttl, c.mss)
    return dmac + smac + b"\x08\x00" + ip_header(cc, ident, 20 + len(seg)) + seg


@dataclass
class Parsed:
    dmac: bytes
    smac: bytes
    sip: int
    dip: int
    sport: int
    dport: int
    seq: int
    ack: int
    flags: int
    win: int
    ident: int
    ttl: int
    payload: bytes
    options: bytes
    ip_ok: bool
    tcp_ok: bool
    df: bool

    @property
    def ok(self) -> bool:
        return self.ip_ok and self.tcp_ok


def parse(fr: bytes) -> Parsed:
    """Parse and verify an Ethernet/IPv4/TCP frame (no FCS). The checks are the receiver's: the header sums to 0xFFFF, the segment with the pseudo-header too."""
    if len(fr) < HDRLEN or fr[12:14] != b"\x08\x00" or fr[14] != 0x45 or fr[23] != 6:
        raise ValueError("not an Ethernet/IPv4/TCP frame without IP options")
    ip = fr[14:34]
    tl = int.from_bytes(fr[16:18], "big")
    seg = fr[34:14 + tl]
    off = (seg[12] >> 4) * 4
    pseudo = fr[26:34] + bytes([0, 6]) + len(seg).to_bytes(2, "big")
    return Parsed(fr[0:6], fr[6:12], int.from_bytes(fr[26:30], "big"), int.from_bytes(fr[30:34], "big"),
                  int.from_bytes(seg[0:2], "big"), int.from_bytes(seg[2:4], "big"), int.from_bytes(seg[4:8], "big"), int.from_bytes(seg[8:12], "big"),
                  seg[13], int.from_bytes(seg[14:16], "big"), int.from_bytes(fr[18:20], "big"), fr[22], seg[off:], seg[20:off],
                  fold(words_sum(ip)) == 0xFFFF, fold(words_sum(pseudo + seg)) == 0xFFFF, bool(fr[20] & 0x40))


COUNTERS = ("sent", "poison", "ref_arm", "ref_stale", "ref_win", "ref_mss", "busy", "late", "nov", "wrign", "sumerr", "cancel0", "build", "abort")


@dataclass
class FastModel:
    """Untimed model of the block's state and decisions (the bench supplies clock numbers where the age matters)."""
    conn: Conn = field(default_factory=Conn)
    arm_req: bool = False
    valid: bool = False
    snd_nxt: int = 0
    snd_una: int = 0
    snd_wnd: int = 0
    rcv_nxt: int = 0
    rcv_wnd: int = 0
    ip_id: int = 0
    stale_limit: int = 0
    refreshed_at: int = 0          # the clock number of the last refresh write (an arm write or a write to SND_UNA, SND_WND, RCV_NXT, RCV_WND)
    counters: dict = field(default_factory=lambda: {k: 0 for k in COUNTERS})

    def stale(self, go_clk: int) -> bool:
        """age as the block holds it when it samples go at clock number go_clk: the clocks since the refresh write's edge, less one."""
        return self.stale_limit != 0 and (go_clk - self.refreshed_at - 1) > self.stale_limit

    def refusal(self, go_clk: int) -> int:
        if not self.arm_req:
            return REFUSE_NOT_ARMED
        if not self.valid or self.stale(go_clk):
            return REFUSE_STALE
        flight = (self.snd_nxt - self.snd_una) & M32
        if self.snd_wnd < PAYLEN or flight > self.snd_wnd - PAYLEN:
            return REFUSE_WINDOW
        if self.conn.mss < PAYLEN:
            return REFUSE_MSS
        return 0

    def segment(self, payload: bytes) -> bytes:
        return frame(self.conn, self.snd_nxt, self.rcv_nxt, self.rcv_wnd, self.ip_id, payload)

    def complete(self, payload: bytes) -> dict:
        """A segment left unpoisoned: advance, and return the record the block hands back."""
        rec = {"seq": self.snd_nxt, "len": len(payload), "id": self.ip_id, "pay": payload}
        self.snd_nxt = (self.snd_nxt + len(payload)) & M32
        self.ip_id = (self.ip_id + 1) & 0xFFFF
        self.counters["sent"] += 1
        return rec
