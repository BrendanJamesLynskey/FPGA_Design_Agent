"""A pure-Python network for the software side (brief 119): an Exchange, an Owner and a ModelHw (or the RTL's bus) around a World, advanced tick by tick.

Used by tests/test_b119_model.py with the untimed ModelHw, and by the cocotb bench with the real block (the bench supplies the bus and forwards frames).
"""
from __future__ import annotations

from designs.b119_tcp_fast.model import orders, soup
from designs.b119_tcp_fast.model.hwmodel import ModelHw
from designs.b119_tcp_fast.model.softtcp import Exchange, Owner, World
from designs.b119_tcp_fast.model.tcpref import Conn


def peer_view(c: Conn) -> Conn:
    return Conn(dmac=c.smac, smac=c.dmac, sip=c.dip, dip=c.sip, sport=c.dport, dport=c.sport, ttl=64, mss=c.mss)


class Net:
    def __init__(self, bus=None, drop=None, ex_window: int = 8192, hb: int = 1000, rto: int = 400, latency: int = 20, owner_iss: int = 5000, ex_iss: int = 90000,
                 conn: Conn | None = None):
        self.conn = conn or Conn()
        self.world = World(latency, drop)
        self.now = 0
        self.ex = Exchange(peer_view(self.conn), lambda fr: self.world.send("host", fr), iss=ex_iss, rto=rto, window=ex_window, hb_ticks=hb)
        self.ex.listen()
        self.hw = None
        if bus is None:
            self.owner = Owner(self.conn, lambda fr: self.world.send("ex", fr), None, iss=owner_iss, rto=rto, hb_ticks=hb)
            self.hw = ModelHw(self.owner.records, lambda fr: self.world.send("ex", fr))
            self.owner.bus = self.hw
        else:
            self.owner = Owner(self.conn, lambda fr: self.world.send("ex", fr), bus, iss=owner_iss, rto=rto, hb_ticks=hb)
        self.world.sinks["ex"] = lambda fr: self.ex.on_frame(fr, self.world.now)
        self.world.sinks["host"] = self.owner.deliver
        self.sent_payloads: list[bytes] = []

    async def wait(self) -> int:
        """Advance one tick (the untimed stand-in's clock)."""
        self.now += 1
        self.world.step_to(self.now)
        if self.hw is not None:
            self.hw.clk = self.now
        self.ex.poll(self.now)
        return self.now

    async def tick(self) -> int:
        now = await self.wait()
        await self.owner.service(now)
        return now

    async def run(self, ticks: int) -> None:
        for _ in range(ticks):
            await self.tick()

    async def start(self, stale_limit: int = 0) -> None:
        self.now = await self.owner.start_session(self.now, self.wait, stale_limit=stale_limit)

    def order(self, ref: int, qty: int = 100, sym: str = "AAA", px: int = 1_000_000, abort: bool = False):
        pay = orders.payload(ref, qty, sym, px)
        fr = self.hw.order(pay, self.now, abort)
        if fr is not None:
            self.sent_payloads.append(pay)
        return fr
