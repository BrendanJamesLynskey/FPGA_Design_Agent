"""The software side of the TCP fast path (brief 119): a user-space TCP endpoint, the connection owner, and a software OUCH exchange.

Why an own TCP: the fast path writes into the same byte stream as the host's stack, and an operating system's TCP cannot be told that another agent used
sequence space. So the connection is modelled honestly here: a small TCP endpoint (handshake, cumulative ACKs, out-of-order reassembly, retransmission
timer, the RFC 793 acceptability rule for ACK-only segments) that is used for both ends. `Owner` is the host side: it does the handshake and the
SoupBinTCP login in software, hands the connection to the hardware through the register bus, keeps the hardware's window and ACK registers current,
retransmits a fast-path segment from the record the hardware handed back, and takes the sequence space back (disarm, wait for idle, check, send, give back)
whenever it has to send something itself. `Exchange` is the server side: a passive TCP endpoint with a SoupBinTCP 3.00 server and an OUCH 5.0 order
handler (Accepted or Rejected, a heartbeat, a logout). Time is an integer number of ticks (clocks in the RTL bench); the heartbeat interval and the
retransmission timeout are given in ticks, scaled down from one second.

What this does not model: congestion control, selective acknowledgements, delayed ACKs, window scaling, timestamps, connection teardown (FIN), zero-window
probes, IP fragmentation or options. Each is listed in docs/tcp_fast.md under Known gaps.
"""
from __future__ import annotations

import heapq
from collections import Counter
from typing import Awaitable, Callable

from designs.b119_tcp_fast.model import regs, soup, tcpref
from designs.b119_tcp_fast.model.tcpref import Conn, M32

SYN, FIN, RST, PSH, ACK = 0x02, 0x01, 0x04, 0x08, 0x10


def lt(a: int, b: int) -> bool:
    return a != b and ((b - a) & M32) < 0x80000000


def le(a: int, b: int) -> bool:
    return a == b or lt(a, b)


class Endpoint:
    """One end of a TCP connection. `conn` is this end's view: sip/sport are its own, dip/dport the peer's. `tx` takes a raw Ethernet frame."""

    def __init__(self, name: str, conn: Conn, tx: Callable[[bytes], None], iss: int = 1000, rto: int = 400, window: int = 8192, ident_base: int = 0x8000):
        self.name, self.conn, self.tx = name, conn, tx
        self.state = "CLOSED"
        self.iss, self.rto = iss, rto
        self.snd_una = self.snd_nxt = iss
        self.rcv_nxt = 0
        self.snd_wnd = 0
        self.rcv_wnd = window
        self.peer_mss = 536
        self.rtx: list[dict] = []
        self.ooo: dict[int, bytes] = {}
        self.ident = ident_base
        self.stats: Counter = Counter()
        self.last_sent = 0
        self.stream_in = bytearray()       # every in-order byte received, kept for the tests
        self.sent_log: list[tuple[int, bytes]] = []     # every new data segment, whoever sent it (software here, hardware via the record)

    # ---- output
    def _ident(self) -> int:
        v = self.ident
        self.ident = (self.ident + 1) & 0xFFFF
        return v

    def _out(self, seq: int, flags: int, payload: bytes = b"", options: bytes = b"", now: int | None = None) -> None:
        ack = self.rcv_nxt if flags & ACK else 0
        self.tx(tcpref.frame(self.conn, seq, ack, self.rcv_wnd, self._ident(), payload, flags, options))
        self.stats["tx"] += 1

    def send_ack(self, now: int | None = None) -> None:
        self._out(self.snd_nxt, ACK, now=now)
        self.stats["pure_acks"] += 1

    def send_data(self, data: bytes, now: int) -> None:
        """Software sends new bytes: a PSH+ACK segment at SND.NXT, kept until acknowledged."""
        self.rtx.append({"seq": self.snd_nxt, "data": data, "flags": PSH | ACK, "t": now, "tries": 0})
        self.sent_log.append((self.snd_nxt, data))
        self._out(self.snd_nxt, PSH | ACK, data, now=now)
        self.last_sent = now          # SoupBinTCP packets only: an ACK or a retransmission does not count towards the one-second heartbeat rule
        self.snd_nxt = (self.snd_nxt + len(data)) & M32

    def connect(self, now: int) -> None:
        self.state = "SYN_SENT"
        self.rtx.append({"seq": self.iss, "data": b"", "flags": SYN, "t": now, "tries": 0})
        self._out(self.iss, SYN, options=b"\x02\x04" + (self.conn.mss).to_bytes(2, "big"), now=now)
        self.snd_nxt = (self.iss + 1) & M32

    def listen(self) -> None:
        self.state = "LISTEN"

    # ---- retransmission timer
    def poll(self, now: int) -> None:
        if not self.rtx:
            return
        e = self.rtx[0]
        if now - e["t"] >= self.rto * (1 << min(e["tries"], 4)):
            e["t"], e["tries"] = now, e["tries"] + 1
            self.stats["retransmits"] += 1
            self._retransmit(e, now)

    def _retransmit(self, e: dict, now: int) -> None:
        opts = b"\x02\x04" + (self.conn.mss).to_bytes(2, "big") if e["flags"] & SYN else b""
        self._out(e["seq"], e["flags"], e["data"], opts, now=now)

    @staticmethod
    def _end(e: dict) -> int:
        return (e["seq"] + len(e["data"]) + (1 if e["flags"] & (SYN | FIN) else 0)) & M32

    # ---- input
    def on_frame(self, raw: bytes, now: int) -> None:
        try:
            p = tcpref.parse(raw)
        except (ValueError, IndexError):
            self.stats["malformed"] += 1
            return
        if not p.ok:
            self.stats["bad_checksum"] += 1
            return
        c = self.conn
        if (p.sip, p.sport, p.dip, p.dport) != (c.dip, c.dport, c.sip, c.sport):
            self.stats["wrong_connection"] += 1
            return
        if p.flags & RST:
            self.state = "CLOSED"
            return
        if self.state == "LISTEN":
            if p.flags & SYN:
                self.rcv_nxt = (p.seq + 1) & M32
                self.snd_wnd = p.win
                self._take_mss(p)
                self.rtx.append({"seq": self.iss, "data": b"", "flags": SYN | ACK, "t": now, "tries": 0})
                self._out(self.iss, SYN | ACK, options=b"\x02\x04" + (self.conn.mss).to_bytes(2, "big"), now=now)
                self.snd_nxt = (self.iss + 1) & M32
                self.state = "SYN_RCVD"
            return
        if self.state == "SYN_SENT":
            if (p.flags & (SYN | ACK)) == (SYN | ACK) and p.ack == self.snd_nxt:
                self._ack(p, now)
                self.rcv_nxt = (p.seq + 1) & M32
                self.snd_wnd = p.win
                self._take_mss(p)
                self.state = "ESTAB"
                self.send_ack(now)
            return
        if self.state == "SYN_RCVD":
            if (p.flags & ACK) and p.ack == self.snd_nxt:
                self._ack(p, now)
                self.snd_wnd = p.win
                self.state = "ESTAB"
            else:
                return
        # ESTAB
        if p.flags & SYN:
            return
        if p.payload:
            self._data(p, now)
        elif lt(p.seq, self.rcv_nxt):
            self.stats["old_pure_ack_dropped"] += 1     # RFC 793: an unacceptable segment is not processed (a pure ACK is not answered, so no ping-pong)
            return
        if p.flags & ACK:
            self._ack(p, now)
            self.snd_wnd = p.win

    def _take_mss(self, p: tcpref.Parsed) -> None:
        o = p.options
        i = 0
        while i + 1 < len(o):
            if o[i] == 0:
                break
            if o[i] == 1:
                i += 1
                continue
            if o[i] == 2 and o[i + 1] == 4:
                self.peer_mss = int.from_bytes(o[i + 2:i + 4], "big")
            i += max(2, o[i + 1])

    def _ack(self, p: tcpref.Parsed, now: int) -> None:
        a = p.ack
        if lt(self.snd_una, a) and le(a, self.snd_nxt):
            self.snd_una = a
            self.rtx = [e for e in self.rtx if not le(self._end(e), a)]
            for e in self.rtx:
                e["tries"] = 0
            self.stats["acks_advancing"] += 1
        elif a == self.snd_una and not p.payload and self.rtx:
            self.stats["dup_acks"] += 1

    def _data(self, p: tcpref.Parsed, now: int) -> None:
        seq, d = p.seq, p.payload
        if lt(seq, self.rcv_nxt):                          # old or partly old
            skip = (self.rcv_nxt - seq) & M32
            if skip >= len(d):
                self.stats["old_data"] += 1
                self.on_ack_needed(now)
                return
            seq, d = self.rcv_nxt, d[skip:]
        if seq == self.rcv_nxt:
            self._deliver(d, now)
            while self.rcv_nxt in self.ooo:
                self._deliver(self.ooo.pop(self.rcv_nxt), now)
        else:
            self.ooo[seq] = d
            self.stats["out_of_order"] += 1
        self.on_ack_needed(now)

    def _deliver(self, d: bytes, now: int) -> None:
        self.rcv_nxt = (self.rcv_nxt + len(d)) & M32
        self.stream_in += d
        self.on_data(d, now)

    def on_ack_needed(self, now: int) -> None:
        self.send_ack(now)

    def on_data(self, d: bytes, now: int) -> None:
        pass


class Exchange(Endpoint):
    """A SoupBinTCP 3.00 server with an OUCH 5.0 order handler, on a passive TCP endpoint. Every data segment is acknowledged at once."""

    def __init__(self, conn: Conn, tx, iss: int = 90000, rto: int = 400, window: int = 8192, hb_ticks: int = 1000, symbols=("AAA", "BBB", "CCC", "DDD", "ZZZZ", "A", "QQQQQQQQ"),
                 users=None, session: str = "SESS000001", max_qty: int = 1_000_000):
        super().__init__("exchange", conn, tx, iss, rto, window, ident_base=0x4000)
        self.stream = soup.Stream()
        self.users = users or {"USER01": "PASSWORD01"}
        self.session, self.hb_ticks, self.max_qty = session, hb_ticks, max_qty
        self.symbols = {soup.alpha(s, 8) for s in symbols}
        self.logged_in = False
        self.next_seq = 1                 # SoupBinTCP sequence number of the next Sequenced Data packet
        self.last_userref = 0
        self.oref = 1000
        self.orders: list[dict] = []      # every Enter Order handled: fields, arrival tick, reply kind
        self.dup_orders = 0
        self.client_hbs = 0
        self.last_rx = 0
        self.logout = False
        self.events: list[str] = []

    def on_data(self, d: bytes, now: int) -> None:
        self.last_rx = now
        for t, body in self.stream.feed(d):
            if t == b"L":
                self._login(body, now)
            elif t == b"U" and self.logged_in:
                self._order(body, now)
            elif t == b"R":
                self.client_hbs += 1
            elif t == b"O":
                self.logout = True
                self.events.append("logout")
            elif t == b"+":
                pass
            else:
                self.events.append(f"unexpected packet {t!r}")

    def _login(self, body: bytes, now: int) -> None:
        user, pw = body[:6].decode().strip(), body[6:16].decode().strip()
        if self.users.get(user) == pw:
            self.logged_in = True
            self.send_data(soup.login_accepted(self.session, self.next_seq), now)
            self.events.append("login accepted")
        else:
            self.send_data(soup.login_rejected("A"), now)
            self.events.append("login rejected")

    def _order(self, body: bytes, now: int) -> None:
        try:
            o = soup.parse_enter(body)
        except ValueError as e:
            self.events.append(f"bad enter order: {e}")
            return
        rec = {"tick": now, **o}
        if o["userref"] <= self.last_userref:
            # OUCH 5.0 section 1.2: a UserRefNum lower than the last processed is taken to be a retransmission and ignored
            self.dup_orders += 1
            rec["reply"] = "ignored"
            self.orders.append(rec)
            return
        self.last_userref = o["userref"]
        reason = 0
        if o["qty"] == 0 or o["qty"] >= 1_000_000:
            reason = 0x0013
        elif o["sym"] not in self.symbols:
            reason = 0x0017
        elif o["px"] == 0:
            reason = 0x001D
        elif o["qty"] > self.max_qty:
            reason = 0x0006
        if reason:
            msg = soup.ouch_rejected(now, o["userref"], reason, o["clordid"])
            rec["reply"] = "J"
        else:
            self.oref += 1
            msg = soup.ouch_accepted(now, o["userref"], o["side"], o["qty"], o["sym"], o["px"], o["tif"], o["display"], self.oref, o["cap"], o["ise"], o["cross"],
                                     b"L", o["clordid"])
            rec["reply"] = "A"
        self.orders.append(rec)
        self.next_seq += 1
        self.send_data(soup.sequenced(msg), now)

    def poll(self, now: int) -> None:
        super().poll(now)
        if self.logged_in and self.state == "ESTAB" and now - self.last_sent >= self.hb_ticks:
            self.send_data(soup.server_heartbeat(), now)


class Owner(Endpoint):
    """The host's TCP owner of the connection that the fast path sends on. `bus` has `async write(addr, val)` and `async read(addr)`."""

    def __init__(self, conn: Conn, tx, bus, iss: int = 5000, rto: int = 400, window: int = 8192, hb_ticks: int = 1000, user: str = "USER01", password: str = "PASSWORD01"):
        super().__init__("owner", conn, tx, iss, rto, window, ident_base=0x8000)
        self.bus = bus
        self.hb_ticks, self.user, self.password = hb_ticks, user, password
        self.inbox: list[bytes] = []
        self.records: list[dict] = []
        self.hw_armed = False
        self.stream = soup.Stream()
        self.responses: list[dict] = []
        self.packets: list[tuple[bytes, bytes]] = []
        self.logged_in = False
        self.login_rejected = False
        self.server_hbs = 0
        self.session = ""
        self.errors: list[str] = []
        self.shadow: dict[int, int] = {}      # the live registers as last written
        self.ack_pending = False
        self.now_hint = 0
        self.hw_sends = 0
        self.takeovers = 0
        self.refresh_ticks = 0               # with a stale limit set, the live registers are rewritten at half of it
        self.last_refresh = 0
        self.refresh_writes = 0

    # ---- plumbing
    def deliver(self, raw: bytes) -> None:
        self.inbox.append(raw)

    def on_hw_record(self, rec: dict) -> None:
        self.records.append(rec)

    def on_ack_needed(self, now: int) -> None:
        self.ack_pending = True

    def on_data(self, d: bytes, now: int) -> None:
        for t, body in self.stream.feed(d):
            self.packets.append((t, body))
            if t == b"A" and not self.logged_in:
                self.logged_in, self.session = True, body[:10].decode().strip()
            elif t == b"J":
                self.login_rejected = True
            elif t == b"S":
                self.responses.append(soup.parse_response(body))
            elif t == b"H":
                self.server_hbs += 1

    def _absorb_records(self, now: int) -> None:
        while self.records:
            r = self.records.pop(0)
            if r["seq"] != self.snd_nxt:
                self.errors.append(f"hardware segment at {r['seq']}, software expected {self.snd_nxt}")
                raise AssertionError(self.errors[-1])
            self.rtx.append({"seq": r["seq"], "data": r["pay"], "flags": PSH | ACK, "t": now, "tries": 0})
            self.sent_log.append((r["seq"], r["pay"]))
            self.snd_nxt = (r["seq"] + r["len"]) & M32
            self.last_sent = now
            self.hw_sends += 1

    # ---- the bus
    async def _live(self, addr: int, val: int) -> None:
        val &= M32
        if self.shadow.get(addr) != val:
            await self.bus.write(addr, val)
            self.shadow[addr] = val

    async def _sync_live(self) -> None:
        await self._live(regs.SND_UNA, self.snd_una)
        await self._live(regs.SND_WND, self.snd_wnd)
        await self._live(regs.RCV_NXT, self.rcv_nxt)
        await self._live(regs.RCV_WND, self.rcv_wnd)
        self.last_refresh = self.now_hint

    async def handoff(self, stale_limit: int = 0, ip_id: int = 1) -> None:
        """Give the fast path the connection: static fields, state, then arm; wait until the template is built."""
        c, b = self.conn, self.bus
        await b.write(regs.DMAC_HI, int.from_bytes(c.dmac[:2], "big"))
        await b.write(regs.DMAC_LO, int.from_bytes(c.dmac[2:], "big"))
        await b.write(regs.SMAC_HI, int.from_bytes(c.smac[:2], "big"))
        await b.write(regs.SMAC_LO, int.from_bytes(c.smac[2:], "big"))
        await b.write(regs.SIP, c.sip)
        await b.write(regs.DIP, c.dip)
        await b.write(regs.PORTS, (c.sport << 16) | c.dport)
        await b.write(regs.TTL_MSS, (min(c.mss, self.peer_mss) << 16) | c.ttl)
        await b.write(regs.SND_NXT, self.snd_nxt)
        await b.write(regs.IP_ID, ip_id)
        await b.write(regs.STALE_LIMIT, stale_limit)
        self.refresh_ticks = stale_limit // 2
        self.shadow.clear()
        await self._sync_live()
        await self._arm()

    async def _arm(self) -> None:
        await self.bus.write(regs.CTRL, 1)
        for _ in range(50):
            if (await self.bus.read(regs.CTRL)) & regs.CTRL_VALID:
                self.hw_armed = True
                return
        raise AssertionError("the template never became valid")

    async def take(self, now: int) -> None:
        """Take the sequence space back: disarm, wait for the segment in flight, absorb its record, check SND.NXT against the hardware's."""
        await self.bus.write(regs.CTRL, 0)
        self.hw_armed = False
        for _ in range(200):
            if not (await self.bus.read(regs.CTRL)) & regs.CTRL_BUSY:
                break
        else:
            raise AssertionError("the fast path stayed busy")
        self._absorb_records(now)
        hw = await self.bus.read(regs.SND_NXT)
        if hw != self.snd_nxt:
            self.errors.append(f"SND.NXT: hardware {hw}, software {self.snd_nxt}")
            raise AssertionError(self.errors[-1])
        self.takeovers += 1

    async def give(self, ip_id: int | None = None) -> None:
        await self.bus.write(regs.SND_NXT, self.snd_nxt)
        await self._sync_live()
        await self._arm()

    async def send_by_software(self, data: bytes, now: int) -> None:
        was = self.hw_armed
        if was:
            await self.take(now)
        self.send_data(data, now)
        if was:
            await self.give()

    # ---- the service loop: call once per tick
    async def service(self, now: int) -> None:
        self.now_hint = now
        self._absorb_records(now)
        inbox, self.inbox = self.inbox, []
        for raw in inbox:
            self.on_frame(raw, now)
        if self.hw_armed and (inbox or self.ack_pending):
            await self._sync_live()
        if self.ack_pending:
            self.ack_pending = False
            if self.hw_armed:
                if not (await self.bus.read(regs.CTRL)) & regs.CTRL_BUSY:
                    hw = await self.bus.read(regs.SND_NXT)
                    self._absorb_records(now)
                    self._out(hw, ACK, now=now)
                    self.stats["pure_acks"] += 1
                else:
                    self.ack_pending = True        # a segment is in flight: try again next tick (its own ACK field is the last one written)
            else:
                self.send_ack(now)
        if self.hw_armed and self.refresh_ticks and now - self.last_refresh >= self.refresh_ticks:
            await self.bus.write(regs.RCV_NXT, self.rcv_nxt)       # the same value again: any live-register write restarts the block's age counter
            self.last_refresh, self.refresh_writes = now, self.refresh_writes + 1
        self.poll(now)
        if self.state == "ESTAB" and self.logged_in and now - self.last_sent >= self.hb_ticks:
            await self.send_by_software(soup.client_heartbeat(), now)

    async def start_session(self, now: int, wait: Callable[[], Awaitable[int]], stale_limit: int = 0, ip_id: int = 1) -> int:
        """Handshake, login, hand over. `wait` advances time by one tick and returns the new time (the bench's clock)."""
        self.connect(now)
        while self.state != "ESTAB":
            now = await wait()
            await self.service(now)
        self.send_data(soup.login_request(self.user, self.password, "", 0), now)
        while not self.logged_in and not self.login_rejected:
            now = await wait()
            await self.service(now)
        if self.login_rejected:
            raise AssertionError("login rejected")
        await self.handoff(stale_limit=stale_limit, ip_id=ip_id)
        return now


class World:
    """Delivery of frames between the endpoints and the hardware, in ticks, with a drop hook: drop(frame, dest, index) -> True drops it."""

    def __init__(self, latency: int = 20, drop: Callable[[bytes, str, int], bool] | None = None):
        self.latency, self.drop = latency, drop
        self.now = 0
        self.q: list = []
        self.n = 0
        self.sinks: dict[str, Callable[[bytes], None]] = {}
        self.sent: Counter = Counter()
        self.dropped: list[tuple[str, int, bytes]] = []
        self.log: list[tuple[int, str, bytes]] = []

    def send(self, dest: str, frame: bytes, extra: int = 0) -> None:
        idx = self.sent[dest]
        self.sent[dest] += 1
        if self.drop and self.drop(frame, dest, idx):
            self.dropped.append((dest, idx, frame))
            return
        self.n += 1
        heapq.heappush(self.q, (self.now + self.latency + extra, self.n, dest, frame))
        self.log.append((self.now, dest, frame))

    def step_to(self, now: int) -> None:
        self.now = now
        while self.q and self.q[0][0] <= now:
            _, _, dest, frame = heapq.heappop(self.q)
            self.sinks[dest](frame)
