"""Reference model of arp_responder, written from RFC 826 and the entry's contract (ip.yaml), not from the RTL.

Receive: an ARP packet for Ethernet/IPv4 (hardware type 1, protocol 0x0800, lengths 6 and 4, operation 1 or 2) in an
EtherType 0x0806 frame of at least 42 bytes. RFC 826's order: if the sender is in the table, update it; if we are the
target, add it when it is not there; if it is a request, reply. A sender of 0.0.0.0 is never learnt.
Cache replacement (the contract): a free slot (the lowest), else the slots in turn.
"""
from __future__ import annotations

import struct

from flow.net import inet

BCAST = b"\xff" * 6


def parse(frame: bytes, bad: bool = False):
    if bad or len(frame) < 42 or frame[12:14] != b"\x08\x06":
        return None
    htype, ptype, hl, pl, op = struct.unpack(">HHBBH", frame[14:22])
    if (htype, ptype, hl, pl) != (1, 0x0800, 6, 4) or op not in (1, 2):
        return None
    return {"op": op, "sha": frame[22:28], "spa": frame[28:32], "tha": frame[32:38], "tpa": frame[38:42]}


def reply(own_mac: bytes, own_ip: bytes, req: dict) -> bytes:
    return inet.eth(req["sha"], own_mac, 0x0806, inet.arp(2, own_mac, own_ip, req["sha"], req["spa"]))


def request(own_mac: bytes, own_ip: bytes, target: bytes) -> bytes:
    return inet.eth(BCAST, own_mac, 0x0806, inet.arp(1, own_mac, own_ip, b"\x00" * 6, target))


class Arp:
    def __init__(self, own_mac: bytes, own_ip: bytes, cache_n: int):
        self.mac, self.ip, self.n = own_mac, own_ip, cache_n
        self.slots: list[tuple[bytes, bytes] | None] = [None] * cache_n
        self.rr = 0

    def find(self, ip: bytes):
        for i, s in enumerate(self.slots):
            if s and s[0] == ip:
                return i
        return None

    def rx(self, frame: bytes, bad: bool = False) -> list[bytes]:
        """Frames sent in answer (zero or one reply)."""
        p = parse(frame, bad)
        if p is None:
            return []
        for_me = p["tpa"] == self.ip
        i = self.find(p["spa"])
        if p["spa"] != b"\x00" * 4 and (for_me or i is not None):
            if i is not None:
                self.slots[i] = (p["spa"], p["sha"])
            elif None in self.slots:
                self.slots[self.slots.index(None)] = (p["spa"], p["sha"])
            else:
                self.slots[self.rr] = (p["spa"], p["sha"])
                self.rr = (self.rr + 1) % self.n
        return [reply(self.mac, self.ip, p)] if for_me and p["op"] == 1 else []

    def lookup(self, ip: bytes):
        i = self.find(ip)
        return (True, self.slots[i][1]) if i is not None else (False, None)

    def flush(self):
        self.slots = [None] * self.n
        self.rr = 0
