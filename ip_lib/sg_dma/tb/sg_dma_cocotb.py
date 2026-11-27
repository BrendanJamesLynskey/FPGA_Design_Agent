"""cocotb bench for ip_lib/sg_dma (brief 241): the engine against a memory model with seeded faults.

One `Bench` object advances the whole system a clock at a time, at the falling edge: it drives the inputs, lets the combinational
outputs settle, reads every channel, records the handshakes (valid and ready both high now happen at the next rising edge), and updates its
agents. The agents are an AXI4-Lite master (software), a memory (`Mem`: AXI4 slave over a byte array with read and write latency,
random ready and valid gaps, ordered responses, SLVERR and DECERR windows) and a stream source or sink with random gaps. Every clock
the memory checks the master's AXI rules: INCR only, size equals the beat width (the status write is one 32-bit beat), a burst of at most
MAX_BURST beats that stays inside one 4 KB page, at most OUTSTANDING data bursts in flight, write data only for an address already issued
(this engine's own promise), and an offered address, data or stream beat kept unchanged until it is accepted. A violation is recorded and fails the test.

Environment: SGD_SEED (default 1). The tests are selected by cocotb's COCOTB_TEST_FILTER / the runner's testcase argument.
"""
from __future__ import annotations

import json
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from ip_lib.sg_dma import model as M

SEED = int(os.environ.get("SGD_SEED", "1"))
MEM_BASE = 0x40000000
MEM_SIZE = 1 << 20
RING_OFF = 0x1000


def v(sig) -> int:
    return int(sig.value)


class Mem:
    """AXI4 slave over MEM_SIZE bytes at MEM_BASE. An address outside the window answers DECERR (3). `err_read` and `err_write` map a
    burst's start address to a response code (2 SLVERR) given on the last beat (reads: every beat of that burst)."""

    def __init__(self, dut, rng, p, beat_bytes, max_burst, outstanding):
        self.d, self.rng, self.p = dut, rng, p
        self.bb, self.mb, self.oc = beat_bytes, max_burst, outstanding
        self.mem = bytearray(MEM_SIZE)
        self.err_read: dict[int, int] = {}
        self.err_write: dict[int, int] = {}
        self.rq: list[dict] = []          # accepted reads: addr, beats, beat index, ready_at
        self.wq: list[dict] = []          # accepted write addresses waiting for their data
        self.bq: list[dict] = []          # finished writes waiting to respond
        self.viol: list[str] = []
        self.hold: dict[str, tuple] = {}
        self.bursts: list[tuple] = []     # (kind, addr, beats) of every address accepted, for the tests
        self.ev: list[tuple[int, str]] = []   # (clock, event) for the measurements
        self.max_out = 0
        self.arready = self.awready = self.wready = self.bvalid_now = 0
        self.rvalid = 0
        self.rcur = None

    def off(self, a):
        return a - MEM_BASE

    def inside(self, a, n):
        return MEM_BASE <= a and a + n <= MEM_BASE + MEM_SIZE

    def outstanding(self):
        return len(self.rq) + len(self.wq) + len(self.bq)

    # ---- the slave's outputs for this clock (a function of its own state and the random gaps only)
    def drive(self, now):
        d, rng, p = self.d, self.rng, self.p
        full = self.outstanding() >= self.oc + 1          # one more than the engine may have in flight: the memory itself never limits it
        self.arready = int(rng.random() < p["arready"] and not full)
        self.awready = int(rng.random() < p["awready"] and not full)
        self.wready = int(bool(self.wq) and rng.random() < p["wready"])
        # read data: the head read, once its latency has passed, offers a beat; held until taken
        if self.rcur is None and self.rq and now >= self.rq[0]["ready_at"] and rng.random() < p["rvalid"]:
            self.rcur = self.rq[0]
        rc = self.rcur
        d.m_axi_arready.value = self.arready
        d.m_axi_awready.value = self.awready
        d.m_axi_wready.value = self.wready
        if rc is not None:
            a = rc["addr"] + rc["i"] * self.bb
            d.m_axi_rvalid.value = 1
            d.m_axi_rdata.value = int.from_bytes(self.mem[self.off(a):self.off(a) + self.bb], "little") if self.inside(a, self.bb) else 0
            d.m_axi_rresp.value = rc["resp"] if self.inside(a, self.bb) else 3
            d.m_axi_rlast.value = int(rc["i"] == rc["beats"] - 1)
        else:
            d.m_axi_rvalid.value = 0
            d.m_axi_rdata.value = 0
            d.m_axi_rresp.value = 0
            d.m_axi_rlast.value = 0
        if self.bq and now >= self.bq[0]["ready_at"] and (self.bvalid_now or rng.random() < p["bvalid"]):
            self.bvalid_now = 1
            d.m_axi_bvalid.value = 1
            d.m_axi_bresp.value = self.bq[0]["resp"]
        else:
            d.m_axi_bvalid.value = 0
            d.m_axi_bresp.value = 0

    # ---- after settling: what the master drove, and the handshakes
    def sample(self, now):
        d = self.d
        mv = lambda s: v(getattr(d, s))
        # rules on the address channels
        for ch, pre in (("ar", "m_axi_ar"), ("aw", "m_axi_aw")):
            valid, ready = mv(pre + "valid"), (self.arready if ch == "ar" else self.awready)
            payload = (mv(pre + "addr"), mv(pre + "len"), mv(pre + "size"), mv(pre + "burst"))
            if self.hold.get(ch) is not None and (not valid or payload != self.hold[ch]):
                self.viol.append(f"{now}: {ch} offer withdrawn or changed before it was accepted")
            self.hold[ch] = payload if (valid and not ready) else None
            if valid and ready:
                addr, ln, size, burst = payload
                beats = ln + 1
                if burst != 1:
                    self.viol.append(f"{now}: {ch} burst type {burst} (INCR only)")
                is_status = ch == "aw" and ln == 0 and size == 2
                is_desc = ch == "ar" and beats == 16 // self.bb and self.desc_range(addr)
                if not is_status and size != self.bb.bit_length() - 1:
                    self.viol.append(f"{now}: {ch} size {size}, beat is {self.bb} bytes")
                nbytes = beats << size
                if (addr & 0xFFF) + nbytes > 4096:
                    self.viol.append(f"{now}: {ch} burst at {addr:#x} of {nbytes} bytes crosses a 4 KB boundary")
                if beats > self.mb and not is_desc:
                    self.viol.append(f"{now}: {ch} burst of {beats} beats, MAX_BURST {self.mb}")
                if addr % (1 << size):
                    self.viol.append(f"{now}: {ch} address {addr:#x} not aligned to its size")
                self.bursts.append((ch, addr, beats, size, now))
        return mv

    def desc_range(self, a):
        return MEM_BASE + RING_OFF <= a < MEM_BASE + RING_OFF + 0x1000

    def edge(self, now, mv):
        """Apply this clock's handshakes (called after sample, i.e. what happens at the coming rising edge)."""
        d, rng, p = self.d, self.rng, self.p
        if mv("m_axi_arvalid") and self.arready:
            ln, size, addr = mv("m_axi_arlen"), mv("m_axi_arsize"), mv("m_axi_araddr")
            resp = self.err_read.get(addr, 0)
            if not self.inside(addr, (ln + 1) << size):
                resp = 3
            self.rq.append({"addr": addr, "beats": ln + 1, "i": 0, "resp": resp, "ready_at": now + p["rlat"]})
            self.ev.append((now, "ar_desc" if self.desc_range(addr) else "ar"))
        if mv("m_axi_awvalid") and self.awready:
            ln, size, addr = mv("m_axi_awlen"), mv("m_axi_awsize"), mv("m_axi_awaddr")
            resp = self.err_write.get(addr, 0)
            if not self.inside(addr, (ln + 1) << size):
                resp = 3
            self.wq.append({"addr": addr, "beats": ln + 1, "i": 0, "size": size, "resp": resp})
            self.ev.append((now, "aw_status" if self.desc_range(addr) else "aw"))
        if mv("m_axi_wvalid"):
            key = "w"
            payload = (mv("m_axi_wdata"), mv("m_axi_wstrb"), mv("m_axi_wlast"))
            if self.hold.get(key) is not None and self.hold[key] != payload:
                self.viol.append(f"{now}: w data changed before it was accepted")
            self.hold[key] = payload if not self.wready else None
            if not self.wq:
                self.viol.append(f"{now}: write data with no address issued")
        elif self.hold.get("w") is not None:
            self.viol.append(f"{now}: wvalid withdrawn before it was accepted")
            self.hold["w"] = None
        if mv("m_axi_wvalid") and self.wready and self.wq:
            w = self.wq[0]
            data, strb, last = mv("m_axi_wdata"), mv("m_axi_wstrb"), mv("m_axi_wlast")
            if last != int(w["i"] == w["beats"] - 1):
                self.viol.append(f"{now}: wlast {last} on beat {w['i']} of {w['beats']}")
            a = w["addr"] + w["i"] * (1 << w["size"]) if w["beats"] > 1 else w["addr"]
            base = a - a % self.bb
            if w["resp"] == 0 and self.inside(base, self.bb):
                o = self.off(base)
                for b in range(self.bb):
                    if (strb >> b) & 1:
                        self.mem[o + b] = (data >> (8 * b)) & 0xFF
            if not (w["beats"] == 1 and self.desc_range(w["addr"])):
                self.ev.append((now, "wbeat"))
            w["i"] += 1
            if w["i"] == w["beats"]:
                self.wq.pop(0)
                self.bq.append({"resp": w["resp"], "ready_at": now + p["wlat"]})
        if self.rcur is not None and mv("m_axi_rready") and v(d.m_axi_rvalid):
            rc = self.rcur
            if not self.desc_range(rc["addr"]):
                self.ev.append((now, "rbeat"))
            rc["i"] += 1
            self.rcur = None
            if rc["i"] == rc["beats"]:
                self.rq.pop(0)
        if mv("m_axi_bvalid") and mv("m_axi_bready"):
            self.ev.append((now, "b"))
            self.bq.pop(0)
            self.bvalid_now = 0
        self.max_out = max(self.max_out, len(self.rq) + len(self.wq) + len(self.bq))


class Bench:
    def __init__(self, dut, p=None, seed=SEED):
        self.d = dut
        self.rng = random.Random(seed)
        self.P = {k: int(getattr(dut, k).value) for k in ("ADDR_W", "DATA_W", "MAX_BURST", "OUTSTANDING", "DIR")}
        self.bb = self.P["DATA_W"] // 8
        q = {"arready": 1.0, "awready": 1.0, "wready": 1.0, "rvalid": 1.0, "bvalid": 1.0, "rlat": 8, "wlat": 6, "src": 1.0, "snk": 1.0}
        q.update(p or {})
        self.p = q
        self.mem = Mem(dut, self.rng, q, self.bb, self.P["MAX_BURST"], self.P["OUTSTANDING"])
        self.now = 0
        self.lite = None                       # a pending AXI4-Lite access: dict
        self.lite_res = None
        self.src: list[int] = []               # stream beats to send (DIR = 1)
        self.src_i = 0
        self.src_hold = None
        self.sink: list[tuple[int, int]] = []  # (data, last) beats received (DIR = 0)
        self.log: list[tuple[int, str]] = []   # (clock, event) for the measurements
        self.irq_clocks: list[int] = []
        self.irq_done: list[int] = []         # DONE_COUNT (read from the design) at each rising edge of irq
        self.stream_viol: list[str] = []
        self.prev_irq = 0
        self.snk_hold = None

    async def start(self):
        d = self.d
        cocotb.start_soon(Clock(d.aclk, 10, unit="ns").start())
        d.aresetn.value = 0
        for s in ("s_axi_awvalid", "s_axi_wvalid", "s_axi_arvalid", "s_axi_bready", "s_axi_rready", "m_axi_arready", "m_axi_awready", "m_axi_wready",
                  "m_axi_bvalid", "m_axi_rvalid", "s_axis_tvalid", "m_axis_tready"):
            getattr(d, s).value = 0
        for s in ("s_axi_awaddr", "s_axi_wdata", "s_axi_wstrb", "s_axi_araddr", "m_axi_bresp", "m_axi_rdata", "m_axi_rresp", "m_axi_rlast", "s_axis_tdata"):
            getattr(d, s).value = 0
        for _ in range(4):
            await RisingEdge(d.aclk)
        await FallingEdge(d.aclk)
        d.aresetn.value = 1

    async def tick(self):
        """One clock: drive at the falling edge, settle, read, record; the rising edge then applies what was read."""
        d = self.d
        await FallingEdge(d.aclk)
        self.now += 1
        now = self.now
        self.mem.drive(now)
        # AXI4-Lite master
        lt = self.lite
        d.s_axi_awvalid.value = int(bool(lt and lt["kind"] == "w" and not lt["aw"]))
        d.s_axi_wvalid.value = int(bool(lt and lt["kind"] == "w" and not lt["w"]))
        d.s_axi_bready.value = int(bool(lt and lt["kind"] == "w" and lt["aw"] and lt["w"]))
        d.s_axi_arvalid.value = int(bool(lt and lt["kind"] == "r" and not lt["ar"]))
        d.s_axi_rready.value = int(bool(lt and lt["kind"] == "r" and lt["ar"]))
        if lt:
            d.s_axi_awaddr.value = lt["addr"]
            d.s_axi_araddr.value = lt["addr"]
            d.s_axi_wdata.value = lt.get("data", 0)
            d.s_axi_wstrb.value = 0xF
        # stream source (DIR = 1) and sink (DIR = 0)
        if self.src_hold is None and self.src_i < len(self.src) and self.rng.random() < self.p["src"]:
            self.src_hold = self.src[self.src_i]
        d.s_axis_tvalid.value = int(self.src_hold is not None)
        d.s_axis_tdata.value = self.src_hold if self.src_hold is not None else 0
        self.snk_rdy = int(self.rng.random() < self.p["snk"])
        d.m_axis_tready.value = self.snk_rdy
        await Timer(1, unit="ns")
        mv = self.mem.sample(now)
        # stream rules on the master port (valid stays, payload stays)
        if self.P["DIR"] == 0:
            cur = (mv("m_axis_tvalid"), mv("m_axis_tdata") if mv("m_axis_tvalid") else None, mv("m_axis_tlast") if mv("m_axis_tvalid") else None)
            if self.snk_hold is not None and (not cur[0] or cur != self.snk_hold):
                self.stream_viol.append(f"{now}: m_axis offer withdrawn or changed before it was accepted")
            self.snk_hold = cur if (cur[0] and not self.snk_rdy) else None
            if cur[0] and self.snk_rdy:
                self.sink.append((cur[1], cur[2]))
        else:
            if mv("s_axis_tready") and self.src_hold is not None:
                self.src_i += 1
                self.src_hold = None
        # AXI4-Lite handshakes
        if lt:
            if lt["kind"] == "w":
                if mv("s_axi_awvalid") and mv("s_axi_awready"):
                    lt["aw"] = 1
                if mv("s_axi_wvalid") and mv("s_axi_wready"):
                    lt["w"] = 1
                if v(d.s_axi_bvalid) and v(d.s_axi_bready):
                    assert v(d.s_axi_bresp) == 0
                    self.lite_res = "ok"
            else:
                if mv("s_axi_arvalid") and mv("s_axi_arready"):
                    lt["ar"] = 1
                if v(d.s_axi_rvalid) and v(d.s_axi_rready):
                    assert v(d.s_axi_rresp) == 0
                    self.lite_res = v(d.s_axi_rdata)
        irq = v(d.irq)
        if irq and not self.prev_irq:
            self.irq_clocks.append(now)
            self.irq_done.append(v(d.done_cnt))
        self.prev_irq = irq
        self.mem.edge(now, mv)
        # event log for the measurements: the first beat and the last beat of data, the status write
        for kind, addr, beats, size, t in self.mem.bursts[-2:]:
            pass

    async def lite_op(self, kind, addr, data=0):
        assert self.lite is None
        self.lite = {"kind": kind, "addr": addr, "data": data, "aw": 0, "w": 0, "ar": 0}
        self.lite_res = None
        while self.lite_res is None:
            await self.tick()
        r, self.lite = self.lite_res, None
        # the AXI4-Lite master's own hold rules are trivial here (it holds until accepted); one idle clock follows
        return r

    async def wr(self, addr, data):
        await self.lite_op("w", addr, data & 0xFFFFFFFF)
        if addr == M.HEAD:
            self.log.append((self.now, "head_written"))

    async def rd(self, addr):
        return await self.lite_op("r", addr)

    # ---- software helpers
    def write_desc(self, idx, addr, length, ioc=False):
        o = RING_OFF + idx * 16
        self.mem.mem[o:o + 16] = M.pack(addr, length, ioc)

    def read_status(self, idx):
        o = RING_OFF + idx * 16 + 12
        return int.from_bytes(self.mem.mem[o:o + 4], "little")

    async def setup(self, ring_size, thr=1, irq_en=True):
        await self.wr(M.RING_LO, MEM_BASE + RING_OFF)
        await self.wr(M.RING_HI, 0)
        await self.wr(M.RING_SIZE, ring_size)
        await self.wr(M.IRQ_THRESH, thr)
        await self.wr(M.CTRL, 1 | (2 if irq_en else 0))

    def check_clean(self):
        assert not self.mem.viol, self.mem.viol[:5]
        assert not self.stream_viol, self.stream_viol[:5]
        assert self.mem.max_out <= self.P["OUTSTANDING"], f"{self.mem.max_out} transactions in flight, OUTSTANDING {self.P['OUTSTANDING']}"


def lay_buffers(bb, lengths, start_off=0x10000, align=None):
    """Buffer addresses for the descriptors: beat aligned, packed one after the other with a gap (so some cross 4 KB pages)."""
    out, off = [], start_off
    for ln in lengths:
        out.append(MEM_BASE + off)
        off += ((ln + bb - 1) // bb) * bb + 0x40
        if align:
            off = (off + align - 1) // align * align
    return out


async def run_ring(b: Bench, lengths, ring_size, starts=None, thr=1, ioc=None, chunk=None, poll=6, limit=400000):
    """Software: lay buffers, write descriptors, set up the engine, publish HEAD in chunks that fit the ring (free slots come from the TAIL
    register, the driver contract), wait for each chunk. Returns (the data moved, the status words in order)."""
    bb, DIR = b.bb, b.P["DIR"]
    ioc = ioc or [False] * len(lengths)
    starts = starts or lay_buffers(bb, lengths)
    pattern = bytes(b.rng.getrandbits(8) for _ in range(sum(lengths)))
    if DIR == 0:                                           # sources are in memory, filled with the pattern
        off = 0
        for ad, ln in zip(starts, lengths):
            b.mem.mem[ad - MEM_BASE:ad - MEM_BASE + ln] = pattern[off:off + ln]
            off += ln
    else:
        b.src = M.words(pattern, bb)
    await b.setup(ring_size, thr)
    n, head, done, stat = len(lengths), 0, 0, []
    guard = 0
    while done < n:
        free = ring_size - 1 - (head - done)
        k = min(free, n - head, chunk or free)
        if k > 0:
            for j in range(k):
                b.write_desc((head + j) % ring_size, starts[head + j], lengths[head + j], ioc[head + j])
            head += k
            await b.wr(M.HEAD, head % ring_size)
        for _ in range(poll):
            await b.tick()
        t = await b.rd(M.TAIL)
        fin = (t - done) % ring_size
        for j in range(fin):
            stat.append(b.read_status((done + j) % ring_size))
        done += fin
        guard += 1
        if b.mem.viol or b.stream_viol:
            break
        assert guard * (poll + 6) < limit, f"timeout: done {done} of {n}"
    return pattern, stat


# ---------------------------------------------------------------------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------------------------------------------------------------------
def data_bursts(b: Bench, kind):
    return [(a, n) for ch, a, n, sz, t in b.mem.bursts if ch == kind and not b.mem.desc_range(a)]


def expected_bursts(b, starts, lengths):
    out = []
    for ad, ln in zip(starts, lengths):
        if not M.bad(ad, ln, b.bb):
            out += M.split(ad, ln, b.bb, b.P["MAX_BURST"])
    return out


def check_moved(b: Bench, pattern, starts, lengths):
    """The data moved is the pattern, in order, with the bursts the model predicts; the bytes around each buffer are untouched."""
    bb = b.bb
    if b.P["DIR"] == 0:
        got = b"".join(d.to_bytes(bb, "little") for d, _ in b.sink)
        assert got == pattern, "stream data differs from the source buffers"
        last_at, c = [], 0
        for ln in lengths:
            c += ln // bb
            last_at.append(c - 1)
        assert [i for i, (_, l) in enumerate(b.sink) if l] == last_at, "tlast is not on the last beat of each descriptor"
        assert data_bursts(b, "ar") == expected_bursts(b, starts, lengths), "read bursts differ from the model's split"
    else:
        off = 0
        for ad, ln in zip(starts, lengths):
            o = ad - MEM_BASE
            assert bytes(b.mem.mem[o:o + ln]) == pattern[off:off + ln], f"buffer at {ad:#x} differs"
            assert bytes(b.mem.mem[o + ln:o + ln + 0x20]) == b"\xaa" * 0x20, f"bytes after the buffer at {ad:#x} were written"
            off += ln
        assert data_bursts(b, "aw") == expected_bursts(b, starts, lengths), "write bursts differ from the model's split"
        assert not b.src[b.src_i:], "stream beats left over"


def prefill(b):
    if b.P["DIR"] == 1:
        b.mem.mem[0x10000:] = b"\xaa" * (MEM_SIZE - 0x10000)


def mix_lengths(bb, mb, rng, n):
    """One beat, a few beats, a full burst, a burst plus one beat, several bursts, a whole 4 KB page and a bit more."""
    base = [bb, 2 * bb, mb * bb, (mb + 1) * bb, 3 * mb * bb + bb, 4096, 4096 + 2 * bb, 5 * 4096 + bb]
    out = base[:]
    while len(out) < n:
        out.append(bb * rng.randint(1, 3 * mb + 3))
    return out[:n]


@cocotb.test()
async def basic(dut):
    """Descriptors of many sizes through a small ring (wraps several times): the data, the status words, the burst list, the counters."""
    b = Bench(dut)
    await b.start()
    prefill(b)
    ln = mix_lengths(b.bb, b.P["MAX_BURST"], b.rng, 13)
    st = lay_buffers(b.bb, ln, align=None)
    st[2] = MEM_BASE + 0x30000 + 4096 - 3 * b.bb                       # two buffers placed so a 4 KB page boundary falls inside them
    st[4] = MEM_BASE + 0x34000 + 4096 - b.bb * (b.P["MAX_BURST"] // 2 + 1)
    pat, stat = await run_ring(b, ln, 5, st, thr=1)
    b.check_clean()
    check_moved(b, pat, st, ln)
    assert stat == [M.status(x, False) for x in ln], [hex(s) for s in stat]
    assert await b.rd(M.DONE_COUNT) == len(ln)
    assert await b.rd(M.TAIL) == len(ln) % 5
    assert b.irq_clocks, "no interrupt"


async def reset(b):
    d = b.d
    await FallingEdge(d.aclk)
    d.aresetn.value = 0
    d.s_axis_tvalid.value = 0
    d.m_axi_rvalid.value = 0
    d.m_axi_bvalid.value = 0
    for _ in range(3):
        await RisingEdge(d.aclk)
    await FallingEdge(d.aclk)
    d.aresetn.value = 1


@cocotb.test()
async def backpressure(dut):
    """The same traffic with random gaps on every channel and a slow memory: nothing lost, repeated or reordered; every rule held."""
    for seed, p in ((11, {"arready": 0.4, "awready": 0.4, "wready": 0.5, "rvalid": 0.5, "bvalid": 0.4, "src": 0.5, "snk": 0.5, "rlat": 20, "wlat": 15}),
                    (12, {"arready": 0.9, "awready": 0.9, "wready": 0.3, "rvalid": 0.9, "bvalid": 0.9, "src": 0.3, "snk": 0.9}),
                    (13, {"arready": 0.2, "awready": 0.2, "wready": 1.0, "rvalid": 1.0, "bvalid": 0.2, "src": 1.0, "snk": 0.2, "rlat": 1, "wlat": 1})):
        b = Bench(dut, p, seed=SEED + seed)
        await b.start()
        prefill(b)
        ln = mix_lengths(b.bb, b.P["MAX_BURST"], b.rng, 9)
        st = lay_buffers(b.bb, ln)
        pat, stat = await run_ring(b, ln, 4, st, thr=2)
        b.check_clean()
        check_moved(b, pat, st, ln)
        assert stat == [M.status(x, False) for x in ln]
        dut._log.info("backpressure seed %d: %d clocks", seed, b.now)
        await reset(b)


@cocotb.test()
async def errors(dut):
    """SLVERR on a data burst, DECERR (a buffer outside the memory), a failed descriptor fetch and a failed status write."""
    b = Bench(dut)
    await b.start()
    prefill(b)
    bb, mb = b.bb, b.P["MAX_BURST"]
    ln = [4 * bb, 3 * mb * bb, 2 * bb]
    st = lay_buffers(bb, ln)
    bad_burst = st[1] + mb * bb                       # the second burst of the second descriptor
    (b.mem.err_read if b.P["DIR"] == 0 else b.mem.err_write)[bad_burst] = 2
    pat, stat = await run_ring(b, ln, 8, st)
    b.check_clean()
    s = [M.unpack_status(x) for x in stat]
    assert [x["err"] for x in s] == [False, True, False], stat
    assert s[1]["code"] == 2 and s[1]["bytes"] == ln[1], s[1]
    assert await b.rd(M.ERR_REG) == 0b1010, "ERR register: first response code in [1:0], data error in [3]"
    await b.wr(M.ERR_REG, 0b1000)
    assert await b.rd(M.ERR_REG) == 0b0010
    # a buffer address outside the memory: DECERR on every beat, the engine carries on and reports code 3
    await b.wr(M.ERR_REG, 0xF)
    b.write_desc(3, 0xF0000000, 8 * bb)
    await b.wr(M.HEAD, 4)
    if b.P["DIR"] == 1:
        b.src += [1] * 8
    for _ in range(600):
        await b.tick()
    w = M.unpack_status(b.read_status(3))
    assert w["done"] and w["err"] and w["code"] == 3, w
    assert await b.rd(M.TAIL) == 4
    # a failed descriptor fetch halts the engine, the tail stays, and a clear resumes it
    b.mem.err_read[MEM_BASE + RING_OFF + 4 * 16] = 2
    b.write_desc(4, st[0], 2 * bb)
    if b.P["DIR"] == 1:
        b.src += [2] * 2
    await b.wr(M.HEAD, 5)
    for _ in range(300):
        await b.tick()
    sts = await b.rd(M.STATUS)
    assert sts & 2, "HALTED not set after a failed descriptor fetch"
    assert await b.rd(M.TAIL) == 4 and await b.rd(M.ERR_REG) & 4
    b.mem.err_read.clear()
    await b.wr(M.STATUS, 2)
    for _ in range(300):
        await b.tick()
    assert await b.rd(M.TAIL) == 5 and not (await b.rd(M.STATUS)) & 2
    # a failed status write halts too
    b.mem.err_write[MEM_BASE + RING_OFF + 5 * 16 + 12] = 2
    b.write_desc(5, st[0], 2 * bb)
    if b.P["DIR"] == 1:
        b.src += [3] * 2
    await b.wr(M.HEAD, 6)
    for _ in range(300):
        await b.tick()
    assert (await b.rd(M.STATUS)) & 2 and await b.rd(M.TAIL) == 5, "a failed status write must halt with the tail unchanged"
    assert not b.mem.viol, b.mem.viol[:5]             # the errors are deliberate: only protocol violations count


@cocotb.test()
async def bad_descriptors(dut):
    """Zero length, a length that is not a whole number of beats, a misaligned address: completed with BAD, nothing moved, the engine goes on."""
    b = Bench(dut)
    await b.start()
    prefill(b)
    bb = b.bb
    await b.setup(8)
    base = MEM_BASE + 0x10000
    cases = [(base, 0), (base, bb + 1), (base + 1, 2 * bb), (base, 2 * bb)]
    for i, (a, n) in enumerate(cases):
        b.write_desc(i, a, n)
    if b.P["DIR"] == 1:
        b.src = [7, 8]
    await b.wr(M.HEAD, 4)
    for _ in range(1500):
        await b.tick()
    stat = [b.read_status(i) for i in range(4)]
    assert stat[:3] == [M.status(0, True), M.status(bb + 1, True), M.status(2 * bb, True)], [hex(s) for s in stat]
    assert stat[3] == M.status(2 * bb, False)
    b.check_clean()
    assert data_bursts(b, "ar" if b.P["DIR"] == 0 else "aw") == M.split(base, 2 * bb, bb, b.P["MAX_BURST"]), "a bad descriptor must not touch memory"
    assert await b.rd(M.TAIL) == 4


@cocotb.test()
async def interrupts(dut):
    """Coalescing: an interrupt at once for an IOC descriptor, one per IRQ_THRESH completions while the ring is not empty, one when the ring drains;
    acknowledge by W1C; IRQ_EN gates the pin. DONE_COUNT at each rising edge of irq tells which completion raised it."""
    b = Bench(dut)
    await b.start()
    prefill(b)
    bb = b.bb
    ln = [2 * bb] * 8
    st = lay_buffers(bb, ln)
    pat = bytes(b.rng.getrandbits(8) for _ in range(sum(ln)))
    if b.P["DIR"] == 0:
        for i, (a, n) in enumerate(zip(st, ln)):
            b.mem.mem[a - MEM_BASE:a - MEM_BASE + n] = pat[i * 2 * bb:(i + 1) * 2 * bb]
    else:
        b.src = M.words(pat, bb)
    await b.setup(16, thr=5)
    for i in (0, 1, 2):                               # three published at once, the first with IOC, IRQ_THRESH 5: the interrupt comes with the first completion
        b.write_desc(i, st[i], ln[i], ioc=(i == 0))
    await b.wr(M.HEAD, 3)
    for _ in range(500):
        await b.tick()
    assert b.irq_done == [1], b.irq_done
    assert (await b.rd(M.STATUS)) & 4
    await b.wr(M.STATUS, 4)
    assert not (await b.rd(M.STATUS)) & 4 and v(dut.irq) == 0
    await b.wr(M.IRQ_THRESH, 3)
    for i in range(3, 7):                             # four published at once, IRQ_THRESH 3: one interrupt, with the 3rd of them (completion 6), before the ring drains
        b.write_desc(i, st[i], ln[i])
    await b.wr(M.HEAD, 7)
    for _ in range(800):
        await b.tick()
    assert b.irq_done == [1, 6], b.irq_done
    await b.wr(M.STATUS, 4)
    b.write_desc(7, st[7], ln[7])                     # a lone descriptor fires because the ring drains
    await b.wr(M.HEAD, 8)
    for _ in range(300):
        await b.tick()
    assert b.irq_done == [1, 6, 8] and v(dut.irq) == 1, b.irq_done
    await b.wr(M.CTRL, 1)                             # IRQ_EN off: the pin drops, the status bit stays
    assert v(dut.irq) == 0 and (await b.rd(M.STATUS)) & 4
    b.check_clean()


@cocotb.test()
async def registers(dut):
    """The register map as the datasheet states it: reset values, read-back, read-only registers, W1C bits, holes."""
    b = Bench(dut)
    await b.start()
    for off in (M.CTRL, M.RING_LO, M.RING_HI, M.RING_SIZE, M.HEAD, M.TAIL, M.IRQ_THRESH, M.DONE_COUNT, M.ERR_REG):
        assert await b.rd(off) == 0, f"reset value of {off:#x}"
    assert await b.rd(M.STATUS) == 1, "idle at reset"
    for off, val in ((M.RING_LO, 0x1234567F), (M.RING_HI, 0x9ABCDEF0), (M.RING_SIZE, 0xFFFFFFFF), (M.HEAD, 0x1234), (M.IRQ_THRESH, 0xFFFF0007)):
        await b.wr(off, val)
    assert await b.rd(M.RING_LO) == 0x12345670 and await b.rd(M.RING_HI) == 0x9ABCDEF0
    assert await b.rd(M.RING_SIZE) == 0xFFFF and await b.rd(M.HEAD) == 0x1234 and await b.rd(M.IRQ_THRESH) == 7
    await b.wr(M.TAIL, 5)
    await b.wr(M.DONE_COUNT, 5)
    assert await b.rd(M.TAIL) == 0 and await b.rd(M.DONE_COUNT) == 0, "TAIL and DONE_COUNT are read-only"
    for hole in (0x28, 0x2C, 0x3C):
        await b.wr(hole, 0xFFFFFFFF)
        assert await b.rd(hole) == 0, "a hole reads 0 and ignores writes, both with OKAY"
    assert await b.rd(M.CTRL) == 0
    await b.wr(M.HEAD, 0)                             # RUN with head == tail: the engine stays idle
    await b.wr(M.CTRL, 3)
    assert await b.rd(M.CTRL) == 3
    b.check_clean()


@cocotb.test()
async def measure(dut):
    """One throughput and latency point (environment: SGD_N descriptors of SGD_SIZE bytes, SGD_RLAT, SGD_WLAT, SGD_OUT: a JSON-lines file)."""
    n, size = int(os.environ.get("SGD_N", "8")), int(os.environ.get("SGD_SIZE", "4096"))
    p = {"rlat": int(os.environ.get("SGD_RLAT", "20")), "wlat": int(os.environ.get("SGD_WLAT", "15"))}
    b = Bench(dut, p)
    await b.start()
    prefill(b)
    ln = [size] * n
    st = lay_buffers(b.bb, ln, align=4096)
    pat, stat = await run_ring(b, ln, n + 1, st, thr=n, poll=2)
    b.check_clean()
    check_moved(b, pat, st, ln)
    ev = b.mem.ev
    head_t = [t for t, k in b.log if k == "head_written"][0]
    beats = [t for t, k in ev if k in ("rbeat", "wbeat")]
    first_ar = [t for t, k in ev if k == "ar_desc"][0]
    lastb = [t for t, k in ev if k == "b"][-1]
    first_data_addr = [t for t, k in ev if k in ("ar", "aw")][0]
    out = {"P": b.P, "n": n, "size": size, "rlat": p["rlat"], "wlat": p["wlat"], "beat_bytes": b.bb, "data_beats": len(beats),
           "head_to_first_ar": first_ar - head_t, "head_to_last_b": lastb - head_t, "first_beat": beats[0] - head_t, "last_beat": beats[-1] - head_t,
           "span_beats": beats[-1] - beats[0] + 1, "total_clocks": lastb - head_t,
           "first_data_addr": first_data_addr - head_t, "first_data_addr_to_last_beat": beats[-1] - first_data_addr + 1}
    if os.environ.get("SGD_OUT"):
        with open(os.environ["SGD_OUT"], "a") as f:
            f.write(json.dumps(out) + "\n")
