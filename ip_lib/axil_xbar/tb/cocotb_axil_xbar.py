"""cocotb bench for ip_lib/axil_xbar: cycle-level Python masters and slaves around the RTL, brief 59's AXI4-Lite checker
on every link (axil_xbar_tb.sv).

One coroutine runs the whole bus. At each falling edge it drives every master's and slave's outputs from their state,
waits for the read-only phase, reads the crossbar's settled outputs and so knows exactly which handshakes happen at the
next rising edge. The models then update their state. Nothing races: every handshake is decided from the same values
the RTL sees at that edge.

What is checked (the expected values come from the address map and the slave logs, never from the RTL):
- every write reaches exactly the slave that owns its address, with the same address, data, strobes and protection,
  in each master's order; no slave sees a write or read for an address it does not own;
- every read returns the data and response that the owning slave produced for that very request (each slave's read
  data mixes its own index, the address and its own count, so a misrouted or stale response cannot match);
- slave error responses (SLVERR) pass through unchanged; addresses in no slave's range get DECERR from the crossbar
  itself, with read data 0, and no slave sees them;
- every transfer completes (no deadlock) and no link breaks an AXI4-Lite rule (the checkers' sticky flags);
- with several masters and slaves, transfers to different slaves do overlap in time (the crossbar is not a shared bus),
  and under full contention for one slave the round-robin arbiter serves every master equally (counts within one),
  for reads and for writes;
- a reset with a write and a read in flight leaves no VALID during the reset, no stale response or request after it,
  and the next write completes.
The write-fairness and reset tests came from the independent review of the crossbar (each caught a mutant the other
tests missed: a stuck write arbiter, and busy flags left out of the reset).

Configuration comes in XBAR_CFG (JSON), set by test_axil_xbar_rtl.py.
"""
from __future__ import annotations

import json
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, Timer

OKAY, SLVERR, DECERR = 0, 2, 3


def cfg():
    return json.loads(os.environ["XBAR_CFG"])


def owner(c, addr):
    for s, (b, n) in enumerate(zip(c["bases"], c["bits"])):
        if (addr >> n) == (b >> n):
            return s
    return None


def rdata_of(s, addr, k):
    """What slave s returns for its k-th read of addr: depends on all three, so a wrong route or a stale value fails."""
    return ((s + 1) * 0x9E3779B1 ^ (addr * 0x85EBCA77) ^ (k * 0xC2B2AE3D)) & 0xFFFFFFFF


def slverr_addr(addr):
    return (addr & 0x3C) == 0x3C            # words at offset 0x3C of every 64 bytes answer SLVERR


class Bits:
    """A packed vector: read and write fields of width w at index i."""

    def __init__(self, n, w):
        self.v = [0] * n
        self.w = w

    def pack(self):
        out = 0
        for i, x in enumerate(self.v):
            out |= (x & ((1 << self.w) - 1)) << (i * self.w)
        return out


def field(val, i, w):
    return (int(val) >> (i * w)) & ((1 << w) - 1)


class Master:
    def __init__(self, m, ops, rng, p_valid, p_ready):
        self.m, self.rng, self.pv, self.pr = m, rng, p_valid, p_ready
        self.wq = [o for o in ops if o[0] == "w"]
        self.rq = [o for o in ops if o[0] == "r"]
        self.w = None      # current write: dict(op, aw, w (pending flags), wait_aw, wait_w)
        self.r = None
        self.wdone, self.rdone = [], []      # (op, resp) / (op, resp, data)
        self.bready = 0
        self.rready = 0

    def plan(self):
        if self.w is None and self.wq and self.rng.random() < self.pv:
            op = self.wq.pop(0)
            self.w = {"op": op, "aw": False, "wv": False, "aw_at": self.rng.choice([0, 0, 1, 3]),
                      "w_at": self.rng.choice([0, 0, 1, 3]), "t": 0, "awdone": False, "wdone": False}
        if self.r is None and self.rq and self.rng.random() < self.pv:
            self.r = {"op": self.rq.pop(0), "t": 0, "ar_at": self.rng.choice([0, 0, 2]), "ardone": False}
        if self.w:
            self.w["aw"] = not self.w["awdone"] and self.w["t"] >= self.w["aw_at"] or (self.w["aw"] and not self.w["awdone"])
            self.w["wv"] = not self.w["wdone"] and self.w["t"] >= self.w["w_at"] or (self.w["wv"] and not self.w["wdone"])
        self.bready = int(self.rng.random() < self.pr)
        self.rready = int(self.rng.random() < self.pr)

    def busy(self):
        return bool(self.w or self.r or self.wq or self.rq)


class Slave:
    def __init__(self, s, rng, p_ready, max_lat):
        self.s, self.rng, self.pr, self.max_lat = s, rng, p_ready, max_lat
        self.aw = None      # accepted address (addr, prot)
        self.wd = None      # accepted data (data, strb)
        self.b = None       # [resp, delay]
        self.ar = None      # [addr, delay]
        self.rv = None      # (data, resp)
        self.nreads = {}
        self.writes, self.reads = [], []        # logs: (addr, prot, data, strb) / (addr, prot, data, resp)
        self.awready = self.wready = self.arready = 0

    def plan(self):
        self.awready = int(self.aw is None and self.b is None and self.rng.random() < self.pr)
        self.wready = int(self.wd is None and self.b is None and self.rng.random() < self.pr)
        self.arready = int(self.ar is None and self.rv is None and self.rng.random() < self.pr)


@cocotb.test()
async def xbar_traffic(dut):
    c = cfg()
    N_M, N_S, AW = c["n_m"], c["n_s"], c["addr_w"]
    rng = random.Random(c["seed"])
    amask = (1 << AW) - 1
    # ---- the operations each master will issue (addresses chosen from the map, its holes and edges)
    def pick_addr():
        r = rng.random()
        if r < c.get("p_hole", 0.1) and c["holes"]:
            lo, hi = rng.choice(c["holes"])
            return (rng.randrange(lo, hi + 1) & ~3) & amask
        s = rng.choice(c.get("targets") or list(range(N_S)))
        b, n = c["bases"][s], c["bits"][s]
        off = rng.choice([0, (1 << n) - 4, rng.randrange(0, 1 << n) & ~3, 0x3C % (1 << n)])
        return (b + off) & amask
    masters = []
    for m in range(N_M):
        ops = []
        for k in range(c["ops"]):
            a = pick_addr()
            if rng.random() < 0.5:
                ops.append(("w", a, rng.randrange(8), rng.getrandbits(32), rng.randrange(16), m, k))
            else:
                ops.append(("r", a, rng.randrange(8), None, None, m, k))
        masters.append(Master(m, ops, random.Random(c["seed"] * 31 + m), c["p_valid"], c["p_ready"]))
    slaves = [Slave(s, random.Random(c["seed"] * 77 + s), c["p_sready"], c["max_lat"]) for s in range(N_S)]

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for name in ("s_axil_awaddr", "s_axil_awprot", "s_axil_awvalid", "s_axil_wdata", "s_axil_wstrb", "s_axil_wvalid",
                 "s_axil_bready", "s_axil_araddr", "s_axil_arprot", "s_axil_arvalid", "s_axil_rready",
                 "m_axil_awready", "m_axil_wready", "m_axil_bresp", "m_axil_bvalid", "m_axil_arready", "m_axil_rdata",
                 "m_axil_rresp", "m_axil_rvalid"):
        getattr(dut, name).value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 4)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    await FallingEdge(dut.clk)        # every VALID low at the first edge out of reset (IHI 0022H A3.1.2, checker rule 7)

    overlap_cycles = 0
    busy_cycles = [0] * N_S
    cycles = 0
    limit = c["ops"] * N_M * (40 + c["max_lat"] * 4) + 2000
    while any(m.busy() for m in masters) or any(s.b or s.rv or s.ar or s.aw or s.wd for s in slaves):
        cycles += 1
        assert cycles < limit, f"no progress after {cycles} cycles (deadlock?)"
        for m in masters:
            m.plan()
        for s in slaves:
            s.plan()
        # ---- drive the masters
        P = {k: Bits(N_M, w) for k, w in (("awaddr", AW), ("awprot", 3), ("awvalid", 1), ("wdata", 32), ("wstrb", 4),
                                          ("wvalid", 1), ("bready", 1), ("araddr", AW), ("arprot", 3), ("arvalid", 1),
                                          ("rready", 1))}
        for m in masters:
            i = m.m
            if m.w:
                _, a, prot, d, st, *_ = m.w["op"]
                P["awaddr"].v[i], P["awprot"].v[i], P["awvalid"].v[i] = a, prot, int(m.w["aw"])
                P["wdata"].v[i], P["wstrb"].v[i], P["wvalid"].v[i] = d, st, int(m.w["wv"])
            if m.r:
                _, a, prot, *_ = m.r["op"]
                P["araddr"].v[i], P["arprot"].v[i], P["arvalid"].v[i] = a, prot, int(not m.r["ardone"] and m.r["t"] >= m.r["ar_at"])
            P["bready"].v[i], P["rready"].v[i] = m.bready, m.rready
        for k, b in P.items():
            getattr(dut, f"s_axil_{k}").value = b.pack()
        # ---- drive the slaves
        S = {k: Bits(N_S, w) for k, w in (("awready", 1), ("wready", 1), ("bresp", 2), ("bvalid", 1), ("arready", 1),
                                          ("rdata", 32), ("rresp", 2), ("rvalid", 1))}
        for s in slaves:
            i = s.s
            S["awready"].v[i], S["wready"].v[i], S["arready"].v[i] = s.awready, s.wready, s.arready
            if s.b and s.b[1] == 0:
                S["bvalid"].v[i], S["bresp"].v[i] = 1, s.b[0]
            if s.rv:
                S["rvalid"].v[i], S["rdata"].v[i], S["rresp"].v[i] = 1, s.rv[0], s.rv[1]
        for k, b in S.items():
            getattr(dut, f"m_axil_{k}").value = b.pack()
        await ReadOnly()
        # ---- what happens at the next rising edge
        awr, wr, bv, br = int(dut.s_axil_awready.value), int(dut.s_axil_wready.value), int(dut.s_axil_bvalid.value), 0
        arr, rv = int(dut.s_axil_arready.value), int(dut.s_axil_rvalid.value)
        bresp, rresp, rdat = int(dut.s_axil_bresp.value), int(dut.s_axil_rresp.value), int(dut.s_axil_rdata.value)
        maw, mawv, mw, mwv = int(dut.m_axil_awaddr.value), int(dut.m_axil_awvalid.value), int(dut.m_axil_wdata.value), int(dut.m_axil_wvalid.value)
        mawp, mws = int(dut.m_axil_awprot.value), int(dut.m_axil_wstrb.value)
        mbr, mar, marv, marp, mrr = int(dut.m_axil_bready.value), int(dut.m_axil_araddr.value), int(dut.m_axil_arvalid.value), int(dut.m_axil_arprot.value), int(dut.m_axil_rready.value)
        nbusy = 0
        for s in slaves:
            i = s.s
            act = bool(s.aw or s.wd or s.b or s.ar or s.rv) or bool((mawv >> i) & 1) or bool((marv >> i) & 1)
            nbusy += act
            busy_cycles[i] += act
            if (mawv >> i) & 1 and s.awready:
                s.aw = (field(maw, i, AW), field(mawp, i, 3))
            if (mwv >> i) & 1 and s.wready:
                s.wd = (field(mw, i, 32), field(mws, i, 4))
            if s.b and s.b[1] == 0 and (mbr >> i) & 1:
                s.b = None
            elif s.b and s.b[1] > 0:
                s.b[1] -= 1
            if s.aw and s.wd and s.b is None:
                a = s.aw[0]
                assert owner(c, a) == i, f"slave {i} received a write to {a:#x}, which it does not own"
                s.writes.append((a, s.aw[1], s.wd[0], s.wd[1]))
                s.b = [SLVERR if slverr_addr(a) else OKAY, s.rng.randrange(c["max_lat"] + 1)]
                s.aw = s.wd = None
            if s.rv and (mrr >> i) & 1:
                s.rv = None
            if s.ar and s.ar[1] > 0:
                s.ar[1] -= 1
            elif s.ar and s.rv is None:
                a = s.ar[0]
                k = s.nreads.get(a, 0)
                s.nreads[a] = k + 1
                resp = SLVERR if slverr_addr(a) else OKAY
                s.rv = (rdata_of(i, a, k), resp)
                s.reads.append((a, s.ar[2], s.rv[0], resp))
                s.ar = None
            if (marv >> i) & 1 and s.arready:
                a = field(mar, i, AW)
                assert owner(c, a) == i, f"slave {i} received a read of {a:#x}, which it does not own"
                s.ar = [a, s.rng.randrange(c["max_lat"] + 1), field(marp, i, 3)]
        overlap_cycles += nbusy >= 2
        for m in masters:
            i = m.m
            if m.w:
                m.w["t"] += 1
                if m.w["aw"] and (awr >> i) & 1:
                    m.w["awdone"], m.w["aw"] = True, False
                if m.w["wv"] and (wr >> i) & 1:
                    m.w["wdone"], m.w["wv"] = True, False
                if (bv >> i) & 1:
                    assert m.w["awdone"] and m.w["wdone"], f"master {i}: B before its AW and W handshakes"
                    if m.bready:
                        m.wdone.append((m.w["op"], field(bresp, i, 2)))
                        m.w = None
            elif (bv >> i) & 1:
                raise AssertionError(f"master {i}: BVALID with no write outstanding")
            if m.r:
                m.r["t"] += 1
                if not m.r["ardone"] and m.r["t"] - 1 >= m.r["ar_at"] and (arr >> i) & 1:
                    m.r["ardone"] = True
                if (rv >> i) & 1:
                    assert m.r["ardone"], f"master {i}: R before its AR handshake"
                    if m.rready:
                        m.rdone.append((m.r["op"], field(rresp, i, 2), field(rdat, i, 32)))
                        m.r = None
            elif (rv >> i) & 1:
                raise AssertionError(f"master {i}: RVALID with no read outstanding")
        await FallingEdge(dut.clk)

    # ---- the end-of-run checks
    await Timer(1, unit="ns")
    for _ in range(3):
        await FallingEdge(dut.clk)
    chk = int(dut.chk_any.value)
    assert chk == 0, f"AXI4-Lite rule broken on links {[i for i in range(N_M + N_S) if (chk >> i) & 1]} (0..{N_M - 1} master side)"
    # writes: per slave, the multiset of writes received equals the writes sent to it, and each master's order holds
    for s in slaves:
        sent = sorted((o[1], o[2], o[3], o[4]) for mm in masters for (o, _) in mm.wdone if owner(c, o[1]) == s.s)
        assert sorted(s.writes) == sent, f"slave {s.s}: received writes differ from those sent to it"
    for mm in masters:
        for (o, resp) in mm.wdone:
            s = owner(c, o[1])
            want = DECERR if s is None else (SLVERR if slverr_addr(o[1]) else OKAY)
            assert resp == want, f"master {mm.m} write {o[6]} to {o[1]:#x}: response {resp}, expected {want}"
        order = [o[6] for (o, _) in mm.wdone]
        assert order == sorted(order), f"master {mm.m}: writes completed out of order"
    # reads: each response is one the owning slave produced for that address, consumed once
    pool = {s.s: {} for s in slaves}
    for s in slaves:
        for (a, prot, d, resp) in s.reads:
            pool[s.s].setdefault((a, prot), []).append((d, resp))
    n_reads = 0
    for mm in masters:
        for (o, resp, d) in mm.rdone:
            n_reads += 1
            s = owner(c, o[1])
            if s is None:
                assert (resp, d) == (DECERR, 0), f"master {mm.m} read of hole {o[1]:#x}: got resp {resp} data {d:#x}"
                continue
            cands = pool[s].get((o[1], o[2]), [])
            assert (d, resp) in cands, f"master {mm.m} read {o[1]:#x}: data {d:#x} resp {resp} is not what slave {s} returned"
            cands.remove((d, resp))
    assert all(not v for p in pool.values() for v in p.values()), "a slave answered a read that no master received"
    n_writes = sum(len(m.wdone) for m in masters)
    assert n_writes + n_reads == N_M * c["ops"], "not every operation completed"
    if c.get("expect_overlap"):
        assert overlap_cycles > 0, "transfers to different slaves never overlapped"
    out = {"cycles": cycles, "writes": n_writes, "reads": n_reads, "overlap_cycles": overlap_cycles,
           "decerr": sum(1 for m in masters for (o, r, *_) in m.wdone + m.rdone if r == DECERR)}
    if os.environ.get("XBAR_OUT"):
        with open(os.environ["XBAR_OUT"], "w") as f:
            json.dump(out, f)
    dut._log.info(f"xbar traffic: {out}")


@cocotb.test()
async def xbar_fairness(dut):
    """Every master hammers slave 0 with back-to-back reads; the slave answers at once. Round robin: equal service."""
    c = cfg()
    N_M, N_S, AW = c["n_m"], c["n_s"], c["addr_w"]
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for name in ("s_axil_awvalid", "s_axil_wvalid", "s_axil_bready", "s_axil_arvalid", "m_axil_bvalid", "m_axil_rvalid",
                 "m_axil_awready", "m_axil_wready"):
        getattr(dut, name).value = 0
    dut.s_axil_araddr.value = sum(c["bases"][0] << (m * AW) for m in range(N_M))
    dut.s_axil_rready.value = (1 << N_M) - 1
    dut.m_axil_arready.value = (1 << N_S) - 1
    dut.rst.value = 1
    await ClockCycles(dut.clk, 4)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    await FallingEdge(dut.clk)
    dut.s_axil_arvalid.value = (1 << N_M) - 1
    served = [0] * N_M
    pend = 0
    for _ in range(60 * N_M):
        dut.m_axil_rvalid.value = pend
        dut.m_axil_rdata.value = 0
        dut.m_axil_rresp.value = 0
        await ReadOnly()
        rv = int(dut.s_axil_rvalid.value)
        marv = int(dut.m_axil_arvalid.value)
        for m in range(N_M):
            served[m] += (rv >> m) & 1
        nxt = 0
        for s in range(N_S):
            if (marv >> s) & 1:
                nxt |= 1 << s           # answer the next cycle
        pend = nxt
        await FallingEdge(dut.clk)
    assert max(served) - min(served) <= 1, f"round robin unequal: {served}"
    assert min(served) > 0
    assert int(dut.chk_any.value) == 0
    dut._log.info(f"served per master: {served}")


# ---------------------------------------------------------------- from the independent review
async def _quiet_setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for name in ("s_axil_awaddr", "s_axil_awprot", "s_axil_awvalid", "s_axil_wdata", "s_axil_wstrb", "s_axil_wvalid",
                 "s_axil_bready", "s_axil_araddr", "s_axil_arprot", "s_axil_arvalid", "s_axil_rready",
                 "m_axil_awready", "m_axil_wready", "m_axil_bresp", "m_axil_bvalid", "m_axil_arready", "m_axil_rdata",
                 "m_axil_rresp", "m_axil_rvalid"):
        getattr(dut, name).value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 4)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    await FallingEdge(dut.clk)


@cocotb.test()
async def write_fairness(dut):
    """Every master hammers slave 0 with back-to-back writes (AW and W together); slave 0 answers at once."""
    c = cfg()
    N_M, N_S, AW = c["n_m"], c["n_s"], c["addr_w"]
    await _quiet_setup(dut)
    dut.s_axil_awaddr.value = sum(c["bases"][0] << (m * AW) for m in range(N_M))
    dut.s_axil_bready.value = (1 << N_M) - 1
    dut.m_axil_awready.value = (1 << N_S) - 1
    dut.m_axil_wready.value = (1 << N_S) - 1
    dut.s_axil_wstrb.value = (1 << (4 * N_M)) - 1
    served = [0] * N_M
    aw_pend = 0
    w_pend = 0
    bpend = 0
    for _ in range(80 * N_M):
        dut.s_axil_awvalid.value = (1 << N_M) - 1
        dut.s_axil_wvalid.value = (1 << N_M) - 1
        dut.m_axil_bvalid.value = bpend
        await ReadOnly()
        bv = int(dut.s_axil_bvalid.value)
        mawv, mwv = int(dut.m_axil_awvalid.value), int(dut.m_axil_wvalid.value)
        for m in range(N_M):
            served[m] += (bv >> m) & 1
        aw_pend |= mawv
        w_pend |= mwv
        nb = aw_pend & w_pend & ~bpend
        bpend = nb
        aw_pend &= ~nb
        w_pend &= ~nb
        await FallingEdge(dut.clk)
    dut._log.info(f"write served per master: {served}")
    assert max(served) - min(served) <= 1, f"write round robin unequal: {served}"
    assert min(served) > 0
    assert int(dut.chk_any.value) == 0


@cocotb.test()
async def reset_mid_transfer(dut):
    """Writes and reads in flight to stalled slaves; reset; then the crossbar must start clean: no VALID during reset,
    no stale B or R afterwards, and a new transfer completes."""
    c = cfg()
    N_M, N_S, AW = c["n_m"], c["n_s"], c["addr_w"]
    await _quiet_setup(dut)
    # master 0 writes slave 0 and reads slave 1 (or slave 0); slaves accept the address but never answer
    tgt_r = 1 if N_S > 1 else 0
    dut.s_axil_awaddr.value = c["bases"][0]
    dut.s_axil_araddr.value = c["bases"][tgt_r]
    dut.s_axil_wstrb.value = 0xF
    dut.s_axil_awvalid.value = 1
    dut.s_axil_wvalid.value = 1
    dut.s_axil_arvalid.value = 1
    dut.m_axil_awready.value = (1 << N_S) - 1
    dut.m_axil_wready.value = (1 << N_S) - 1
    dut.m_axil_arready.value = (1 << N_S) - 1
    dut.s_axil_bready.value = 1
    dut.s_axil_rready.value = 1
    for _ in range(3):
        await ReadOnly()
        if int(dut.s_axil_awready.value) & 1:
            pass
        await FallingEdge(dut.clk)
    dut.s_axil_awvalid.value = 0
    dut.s_axil_wvalid.value = 0
    dut.s_axil_arvalid.value = 0
    for _ in range(4):
        await FallingEdge(dut.clk)
    # reset with both transfers outstanding at the slaves
    dut.rst.value = 1
    for _ in range(3):
        await FallingEdge(dut.clk)
        await ReadOnly()
        assert int(dut.m_axil_awvalid.value) == 0 and int(dut.m_axil_wvalid.value) == 0 and int(dut.m_axil_arvalid.value) == 0
        assert int(dut.s_axil_bvalid.value) == 0 and int(dut.s_axil_rvalid.value) == 0
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    # the old slaves' late responses must not reach the master (slaves were reset too: they never answer)
    for _ in range(10):
        await FallingEdge(dut.clk)
        await ReadOnly()
        assert int(dut.s_axil_bvalid.value) == 0, "stale B after reset"
        assert int(dut.s_axil_rvalid.value) == 0, "stale R after reset"
        assert int(dut.m_axil_awvalid.value) == 0 and int(dut.m_axil_arvalid.value) == 0, "stale request after reset"
    await FallingEdge(dut.clk)
    # a new write after reset completes with OKAY
    dut.s_axil_awvalid.value = 1
    dut.s_axil_wvalid.value = 1
    done = False
    got_aw = got_w = False
    for _ in range(20):
        await ReadOnly()
        acc = int(dut.s_axil_awready.value) & 1
        maw, mw = int(dut.m_axil_awvalid.value) & 1, int(dut.m_axil_wvalid.value) & 1
        b = int(dut.s_axil_bvalid.value) & 1
        await FallingEdge(dut.clk)
        if acc:
            dut.s_axil_awvalid.value = 0
            dut.s_axil_wvalid.value = 0
        got_aw |= bool(maw)
        got_w |= bool(mw)
        dut.m_axil_bvalid.value = 1 if (got_aw and got_w) else 0
        if b:
            done = True
            break
    assert done, "a write after reset did not complete"
    dut.m_axil_bvalid.value = 0
    await ClockCycles(dut.clk, 3)
