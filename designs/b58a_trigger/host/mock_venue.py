"""Mock venue: our own stand-in for a market on a bench. It publishes Bench Feed v1 market data and accepts
the board's mock orders. It models no real market, protocol or firm; prices and sizes are stimulus values.

Two uses, one code path for the data:
- in simulation (designs/b58a_trigger/tests/b58a_cocotb.py) a `Venue` makes the frames the RTL receives and checks the
  orders the RTL sends;
- on the bench, `python3 -m designs.b58a_trigger.host.mock_venue --board-ip ... --bind-ip ...` sends the same packets
  over UDP from a PC on an isolated bench network and receives the orders (the board answers ARP for its address).

The venue keeps its own top of book per instrument and makes each message consistent with it (a MODIFY or TRADE is
at the current best price), so the board's book and the venue's agree message by message; the tests check that.
"""

from __future__ import annotations

import argparse
import random
import socket
import struct
import time
from dataclasses import dataclass, field

from designs.b58a_trigger.model import benchfeed as bf


@dataclass
class Venue:
    seed: int = 1
    ninst: int = 8
    mid: int = 10000                    # hundredths
    spread: int = 300
    seq: int = 1
    book: dict[int, list[int]] = field(default_factory=dict)   # inst -> [bid_px, bid_sz, ask_px, ask_sz]
    orders: list[bf.Order] = field(default_factory=list)
    cancels: list[bf.Order] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    def _msg(self) -> bf.Msg:
        r = self.rng
        inst = r.randrange(self.ninst)
        side = r.randrange(2)
        e = self.book.setdefault(inst, [0, 0, 0, 0])
        i = 2 if side else 0
        has = e[i + 1] != 0
        kind = r.choices([bf.ADD, bf.MODIFY, bf.CANCEL, bf.TRADE], [5, 2, 1, 2])[0] if has else bf.ADD
        if kind == bf.ADD:
            base = self.mid + (self.spread // 2 if side else -self.spread // 2)
            px = max(1, base + r.randrange(-self.spread, self.spread + 1))
            sz = r.randrange(1, 200)
            e[i], e[i + 1] = px, sz
        elif kind == bf.MODIFY:
            px, sz = e[i], r.randrange(1, 200)
            e[i + 1] = sz
        elif kind == bf.CANCEL:
            px, sz = e[i], e[i + 1]
            e[i], e[i + 1] = 0, 0
        else:
            px, sz = e[i], r.randrange(1, e[i + 1] + 1)
            e[i + 1] -= sz
            if e[i + 1] == 0:
                e[i] = 0
        return bf.Msg(kind, side, inst, px, sz, 0)

    def packet_msgs(self, n: int) -> tuple[int, list[bf.Msg]]:
        seq = self.seq
        msgs = [self._msg() for _ in range(n)]
        for k, m in enumerate(msgs):
            m.ref = seq + k
        self.seq += n
        return seq, msgs

    def payload(self, n: int) -> bytes:
        seq, msgs = self.packet_msgs(n)
        return bf.packet(seq, msgs)

    def frame(self, n: int, **kw) -> bytes:
        """A feed frame (no FCS) to the board."""
        seq, msgs = self.packet_msgs(n)
        return bf.feed_frame(seq, msgs, **kw)

    def on_order(self, o: bf.Order) -> None:
        (self.cancels if o.type == bf.CANCEL_ORDER else self.orders).append(o)

    def would_cross(self, o: bf.Order) -> bool:
        """Whether an order would trade against the venue's current book (a statistic only; the venue fills nothing)."""
        e = self.book.get(o.inst, [0, 0, 0, 0])
        return (o.side == bf.BUY and e[3] != 0 and o.price >= e[2]) or (o.side == bf.SELL and e[1] != 0 and o.price <= e[0])


def run_udp(board_ip: str, bind_ip: str, port: int, n_pkts: int, msgs: int, interval_s: float, seed: int) -> dict:
    """Send `n_pkts` feed packets to the board over UDP and collect its orders: the bench run (never on a home network)."""
    v = Venue(seed=seed)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx.bind((bind_ip, bf.VENUE_PORT + 10))
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind((bind_ip, bf.VENUE_PORT))
    rx.settimeout(0.0)
    sent_t: dict[int, float] = {}
    lat: list[float] = []
    for _ in range(n_pkts):
        seq = v.seq
        p = v.payload(msgs)
        sent_t[seq] = time.perf_counter()
        tx.sendto(p, (board_ip, port))
        t_end = time.perf_counter() + interval_s
        while time.perf_counter() < t_end:
            try:
                data, _ = rx.recvfrom(2048)
            except BlockingIOError:
                continue
            if len(data) >= 24:
                t, s, i, px, q, oid = struct.unpack(">BBHIII", data[8:24])
                o = bf.Order(t, s, i, px, q, oid, struct.unpack(">I", data[4:8])[0])
                v.on_order(o)
                lat.append(time.perf_counter() - sent_t[seq])
    return {"packets": n_pkts, "orders": len(v.orders), "cancels": len(v.cancels),
            "host_round_trip_s": sorted(lat)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Mock venue for the bench loop (isolated bench network only).")
    ap.add_argument("--board-ip", default="192.168.58.10")
    ap.add_argument("--bind-ip", default="192.168.58.15")
    ap.add_argument("--port", type=int, default=bf.BOARD_PORT)
    ap.add_argument("--packets", type=int, default=1000)
    ap.add_argument("--msgs", type=int, default=1)
    ap.add_argument("--interval", type=float, default=0.001)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    r = run_udp(a.board_ip, a.bind_ip, a.port, a.packets, a.msgs, a.interval, a.seed)
    print({k: (v if not isinstance(v, list) else len(v)) for k, v in r.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
