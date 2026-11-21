"""SoupBinTCP 3.00 packets and the OUCH 5.0 messages the software exchange sends (brief 119).

Layouts are from the Nasdaq documents (SoupBinTCP 3.00 sections 2.2 and 2.3; OUCH 5.0 sections 2.1, 3.2 and 3.8, Appendix C), read for this brief; the fields
of the Enter Order are the ones brief 110's packers build. Padding: Alpha fields are left-justified and right-padded with spaces; the sequence number fields of
the login packets are ASCII and left-padded with spaces (SoupBinTCP 3.00 states this for Login Accepted; for the Login Request this repository assumes the same: UNCONFIRMED).
"""
from __future__ import annotations

import struct

TS_NS = 0


def pkt(t: bytes, body: bytes = b"") -> bytes:
    """Packet Length (the type byte plus the body), type, body."""
    return struct.pack(">H", 1 + len(body)) + t + body


def alpha(s: str | bytes, n: int) -> bytes:
    b = s.encode() if isinstance(s, str) else s
    assert len(b) <= n
    return b + b" " * (n - len(b))


def num20(n: int) -> bytes:
    return str(n).rjust(20).encode()


def login_request(user: str, password: str, session: str = "", seq: int = 0) -> bytes:
    return pkt(b"L", alpha(user, 6) + alpha(password, 10) + alpha(session, 10) + num20(seq))


def login_accepted(session: str, seq: int) -> bytes:
    return pkt(b"A", session.rjust(10).encode() + num20(seq))


def login_rejected(code: str) -> bytes:
    return pkt(b"J", code.encode())


def sequenced(msg: bytes) -> bytes:
    return pkt(b"S", msg)


def unsequenced(msg: bytes) -> bytes:
    return pkt(b"U", msg)


def server_heartbeat() -> bytes:
    return pkt(b"H")


def client_heartbeat() -> bytes:
    return pkt(b"R")


def logout_request() -> bytes:
    return pkt(b"O")


def end_of_session() -> bytes:
    return pkt(b"Z")


def debug(text: str) -> bytes:
    return pkt(b"+", text.encode())


class Stream:
    """Reassembles SoupBinTCP packets from an in-order byte stream (a packet may be split or joined by TCP)."""

    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes) -> list[tuple[bytes, bytes]]:
        self.buf += data
        out = []
        while len(self.buf) >= 3:
            n = struct.unpack(">H", self.buf[:2])[0]
            if n < 1:
                raise ValueError("SoupBinTCP packet length 0")
            if len(self.buf) < 2 + n:
                break
            out.append((bytes(self.buf[2:3]), bytes(self.buf[3:2 + n])))
            del self.buf[:2 + n]
        return out


# ---- OUCH 5.0 messages from the exchange (section 3)
def ouch_accepted(ts: int, userref: int, side: bytes, qty: int, sym: bytes, px: int, tif: bytes, display: bytes, oref: int, cap: bytes, ise: bytes,
                  cross: bytes, state: bytes, clordid: bytes) -> bytes:
    m = (b"A" + struct.pack(">QI", ts, userref) + side + struct.pack(">I", qty) + sym + struct.pack(">Q", px) + tif + display + struct.pack(">Q", oref)
         + cap + ise + cross + state + clordid + struct.pack(">H", 0))
    assert len(m) == 64
    return m


def ouch_rejected(ts: int, userref: int, reason: int, clordid: bytes) -> bytes:
    m = b"J" + struct.pack(">QIH", ts, userref, reason) + clordid + struct.pack(">H", 0)
    assert len(m) == 31
    return m


def parse_enter(m: bytes) -> dict:
    """An Enter Order (type 'O', 47 fixed bytes then the appendage), as brief 110 builds it."""
    if len(m) < 49 or m[:1] != b"O":
        raise ValueError("not an Enter Order")
    alen = struct.unpack(">H", m[45:47])[0]
    if len(m) != 47 + alen:
        raise ValueError("Enter Order length does not match its appendage length")
    return {"userref": struct.unpack(">I", m[1:5])[0], "side": m[5:6], "qty": struct.unpack(">I", m[6:10])[0], "sym": m[10:18],
            "px": struct.unpack(">Q", m[18:26])[0], "tif": m[26:27], "display": m[27:28], "cap": m[28:29], "ise": m[29:30], "cross": m[30:31],
            "clordid": m[31:45], "app": m[47:]}


def parse_response(m: bytes) -> dict:
    if m[:1] == b"A" and len(m) >= 64:
        return {"type": "A", "ts": struct.unpack(">Q", m[1:9])[0], "userref": struct.unpack(">I", m[9:13])[0], "qty": struct.unpack(">I", m[14:18])[0],
                "oref": struct.unpack(">Q", m[36:44])[0], "state": m[47:48], "clordid": m[48:62]}
    if m[:1] == b"J" and len(m) >= 31:
        return {"type": "J", "ts": struct.unpack(">Q", m[1:9])[0], "userref": struct.unpack(">I", m[9:13])[0],
                "reason": struct.unpack(">H", m[13:15])[0], "clordid": m[15:29]}
    raise ValueError("unknown OUCH response")
