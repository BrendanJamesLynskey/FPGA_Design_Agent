"""Wire formats of the standard-protocol trading path (brief 110): packers and parsers, from the public Nasdaq specifications.

Sources (fetched 2026-11-20, not committed; field layouts re-read from the PDFs):
  Nasdaq TotalView-ITCH 5.0 (revision list ends 28 April 2023): section 1.1 System Event, 1.2.1 Stock Directory, 1.3.1 Add Order,
    1.3.2 Add Order with MPID, 1.4.1 Order Executed, 1.4.2 Order Executed With Price, 1.4.3 Order Cancel, 1.4.4 Order Delete,
    1.4.5 Order Replace; "Data Types" (big endian, alpha left-justified and space padded, Price(4) = four implied decimals).
  MoldUDP64 V 1.00 (revision list ends 8/2/24): "Downstream Packet Header" (session 10, sequence number 8, message count 2),
    "Message Block" (length 2, then data); message count 0 = heartbeat, 0xFFFF = end of session.
  OUCH 5.0 (updated October 2025, revision 1.05): section 2.1 Type O Enter Order (47 fixed bytes, appendage length at offset 45),
    Data Types (TagValue element: length, option tag, value), Appendix A optional fields (tag 3 MinQty, tag 4 CustomerType).
  SoupBinTCP version 3.00 (the brief said 4.0; the public document is 3.00): section 1.1 (two byte length, one byte type, payload),
    section 2.3.2 Unsequenced Data Packet (type 'U').
Facts that are read from the documents are marked in docs/spec_notes.md; recalled or assumed ones are marked UNCONFIRMED there.
"""
from __future__ import annotations

import struct

# message lengths (bytes) of the ITCH messages the decoder knows; every other type is skipped by its Mold length
ITCH_LEN = {"S": 12, "R": 39, "A": 36, "F": 40, "E": 31, "C": 36, "X": 23, "D": 19, "U": 35}
ITCH_KEEP = 36          # bytes of a message the hardware keeps (the first 36); the MPID of F and the tail of R are not used
MOLD_HDR = 20
MIN_BLOCK = 12          # smallest message a block may carry (the smallest ITCH 5.0 message is 12 bytes)
EOS = 0xFFFF
SESSION_LEN = 10


def alpha(s: str, n: int) -> bytes:
    """Left-justified ASCII field padded on the right with spaces (ITCH 5.0 and OUCH 5.0 'Data Types')."""
    b = s.encode("ascii")
    assert len(b) <= n
    return b + b" " * (n - len(b))


def _hdr(t: str, locate: int, tracking: int, ts: int) -> bytes:
    return t.encode() + struct.pack(">HH", locate, tracking) + ts.to_bytes(6, "big")


def itch_S(locate: int, ts: int, code: str, tracking: int = 0) -> bytes:
    return _hdr("S", locate, tracking, ts) + code.encode()


def itch_R(locate: int, ts: int, stock: str, tracking: int = 0, tail: bytes | None = None) -> bytes:
    """Stock Directory: 39 bytes; the fields after the symbol are filler here (market category 'Q', normal status, ...)."""
    tail = tail if tail is not None else b"Q" + b"N" + struct.pack(">I", 100) + b"N" + b"C" + b"  " + b"P" + b"N" + b" " + b"1" + b"N" + struct.pack(">I", 0) + b"N"
    m = _hdr("R", locate, tracking, ts) + alpha(stock, 8) + tail
    return m[:39].ljust(39, b" ")


def itch_A(locate: int, ts: int, ref: int, side: str, shares: int, stock: str, price: int, tracking: int = 0) -> bytes:
    return _hdr("A", locate, tracking, ts) + struct.pack(">QcI", ref, side.encode(), shares) + alpha(stock, 8) + struct.pack(">I", price)


def itch_F(locate: int, ts: int, ref: int, side: str, shares: int, stock: str, price: int, mpid: str = "NSDQ", tracking: int = 0) -> bytes:
    return itch_A(locate, ts, ref, side, shares, stock, price, tracking).replace(b"A", b"F", 1) + alpha(mpid, 4)


def itch_E(locate: int, ts: int, ref: int, shares: int, match: int = 1, tracking: int = 0) -> bytes:
    return _hdr("E", locate, tracking, ts) + struct.pack(">QIQ", ref, shares, match)


def itch_C(locate: int, ts: int, ref: int, shares: int, price: int, match: int = 1, printable: str = "Y", tracking: int = 0) -> bytes:
    return _hdr("C", locate, tracking, ts) + struct.pack(">QIQcI", ref, shares, match, printable.encode(), price)


def itch_X(locate: int, ts: int, ref: int, shares: int, tracking: int = 0) -> bytes:
    return _hdr("X", locate, tracking, ts) + struct.pack(">QI", ref, shares)


def itch_D(locate: int, ts: int, ref: int, tracking: int = 0) -> bytes:
    return _hdr("D", locate, tracking, ts) + struct.pack(">Q", ref)


def itch_U(locate: int, ts: int, oref: int, nref: int, shares: int, price: int, tracking: int = 0) -> bytes:
    return _hdr("U", locate, tracking, ts) + struct.pack(">QQII", oref, nref, shares, price)


def itch_other(t: str, n: int, locate: int = 0, ts: int = 0) -> bytes:
    """A message of a type the book ignores (for example P Trade, Q Cross, H Trading Action), n bytes long."""
    return (_hdr(t, locate, 0, ts) + bytes(range(n)))[:n]


def mold_packet(session: bytes, seq: int, msgs: list[bytes], count: int | None = None, trailer: bytes = b"") -> bytes:
    assert len(session) == SESSION_LEN
    n = len(msgs) if count is None else count
    out = session + struct.pack(">QH", seq, n)
    for m in msgs:
        out += struct.pack(">H", len(m)) + m
    return out + trailer


def heartbeat(session: bytes, seq: int) -> bytes:
    return mold_packet(session, seq, [], 0)


def end_of_session(session: bytes, seq: int) -> bytes:
    return mold_packet(session, seq, [], EOS)


def words(pkt: bytes) -> list[tuple[int, int]]:
    """A byte string as 64-bit words, byte 0 in bits 7:0, with the keep mask of each word (the last may be partial)."""
    out = []
    for i in range(0, len(pkt), 8):
        c = pkt[i:i + 8]
        out.append((int.from_bytes(c.ljust(8, b"\0"), "little"), (1 << len(c)) - 1))
    return out


# ---- OUCH 5.0 Enter Order in SoupBinTCP 3.00 Unsequenced Data framing ----
OUCH_FIXED = 47         # offset of the optional appendage in an Enter Order (section 2.1)
TAG_MINQTY, TAG_CUSTTYPE = 3, 4     # Appendix A option tags


def ouch_enter(userref: int, side: str, qty: int, symbol: bytes, price: int, tif: str, display: str, capacity: str, ise: str,
               cross: str, clordid: bytes, minqty: int, custtype: str) -> bytes:
    """Type 'O' Enter Order (56 bytes: 47 fixed plus a 9 byte appendage holding MinQty and CustomerType). Price is 8 bytes in revision 1.05."""
    assert len(symbol) == 8 and len(clordid) == 14
    app = bytes([5, TAG_MINQTY]) + struct.pack(">I", minqty) + bytes([2, TAG_CUSTTYPE]) + custtype.encode()
    m = (b"O" + struct.pack(">I", userref) + side.encode() + struct.pack(">I", qty) + symbol + struct.pack(">Q", price)
         + tif.encode() + display.encode() + capacity.encode() + ise.encode() + cross.encode() + clordid + struct.pack(">H", len(app)) + app)
    assert len(m) == OUCH_FIXED + len(app)
    return m


def soup_unsequenced(msg: bytes) -> bytes:
    """SoupBinTCP Unsequenced Data packet: length (type byte plus payload), 'U', message."""
    return struct.pack(">H", 1 + len(msg)) + b"U" + msg


def clordid(userref: int) -> bytes:
    """ClOrdID of the hardware: 'FDA110' then the order number as eight upper-case hex digits (alphanumeric, 14 bytes)."""
    return b"FDA110" + b"%08X" % userref
