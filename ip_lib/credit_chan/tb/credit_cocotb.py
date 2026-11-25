"""cocotb bench for ip_lib/credit_chan (brief 151) against model.py, clock by clock, plus an independent scoreboard
(the beats that leave are the beats accepted, in order, none lost or repeated; the receiver buffer never overflows).
The top is credit_axis_tb: credit_chan plus the AXI4-Stream rule monitor (axi_tx/rtl/axis_rules.sv) on both ports; any broken rule
fails the run, and tvalid is checked not to depend on tready. Tests: `random_traffic` (source and sink profiles, mid-run resets), `measure` (latency, throughput, capacity, credit round
trip; JSON to $CREDIT_OUT when set). Environment: CREDIT_SEED, CREDIT_CLOCKS."""
from __future__ import annotations

import json
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from ip_lib.credit_chan import model as M

SEED = int(os.environ.get("CREDIT_SEED", "1"))
CLOCKS = int(os.environ.get("CREDIT_CLOCKS", "2000"))


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.dw, self.c, self.lf, self.lb = (int(dut.W.value), int(dut.CREDITS.value), int(dut.LF.value), int(dut.LB.value))
        self.tl, self.tk, self.tu = int(dut.TLAST_EN.value), int(dut.TKEEP_EN.value), int(dut.TUSER_W.value)
        self.kw = max(self.dw // 8, 1)
        self.w = self.dw + self.tl + (self.kw if self.tk else 0) + self.tu      # the packed word
        self.mask = (1 << self.w) - 1
        self.model = M.Chan(self.c, self.lf, self.lb)
        self.accepted: list[int] = []
        self.delivered: list[int] = []
        self.clk_n = 0

    async def start(self):
        d = self.dut
        cocotb.start_soon(Clock(d.aclk, 10, unit="ns").start())
        d.aresetn.value, d.s_axis_tvalid.value, d.m_axis_tready.value = 0, 0, 0
        self.put_data(0)
        await self.reset(3)

    async def reset(self, clocks: int):
        d = self.dut
        d.aresetn.value, d.s_axis_tvalid.value, d.m_axis_tready.value = 0, 0, 0
        for _ in range(clocks):
            await RisingEdge(d.aclk)
        await Timer(1, unit="ns")
        self.model.reset()
        assert self.delivered == self.accepted[:len(self.delivered)], "order or loss before a reset"
        self.accepted, self.delivered = [], []
        d.aresetn.value = 1
        await self.tick(0, 0, 0)               # AXI4-Stream 2.8: tvalid stays low at the first edge after reset is released

    def put_data(self, packed: int):
        """Drive the slave-port signals from a packed word {tuser, tkeep, tlast, tdata}."""
        d = self.dut
        d.s_axis_tdata.value = packed & ((1 << self.dw) - 1)
        d.s_axis_tlast.value = (packed >> self.dw) & 1 if self.tl else 0
        sh = self.dw + self.tl
        d.s_axis_tkeep.value = (packed >> sh) & ((1 << self.kw) - 1) if self.tk else 0
        sh += self.kw if self.tk else 0
        d.s_axis_tuser.value = (packed >> sh) & ((1 << max(self.tu, 1)) - 1) if self.tu else 0

    def get_data(self) -> int:
        d = self.dut
        v = int(d.m_axis_tdata.value)
        if self.tl:
            v |= int(d.m_axis_tlast.value) << self.dw
        sh = self.dw + self.tl
        if self.tk:
            v |= int(d.m_axis_tkeep.value) << sh
            sh += self.kw
        if self.tu:
            v |= int(d.m_axis_tuser.value) << sh
        return v

    def viol(self) -> int:
        return (int(self.dut.viol_s.value) | int(self.dut.viol_m.value)) & 0x7      # rules 0-2 are the protocol's; 3 and 4 are profile rules

    async def tick(self, s_valid: int, s_data: int, m_ready: int):
        d = self.dut
        d.s_axis_tvalid.value, d.m_axis_tready.value = s_valid, m_ready
        self.put_data(s_data)
        await Timer(1, unit="ns")
        s_ready, m_valid = int(d.s_axis_tready.value), int(d.m_axis_tvalid.value)
        m_data = self.get_data() if m_valid else None
        d.m_axis_tready.value = 1 - m_ready                # tvalid must not depend on tready
        await Timer(1, unit="ns")
        assert int(d.m_axis_tvalid.value) == m_valid, f"clock {self.clk_n}: m_axis_tvalid depends on m_axis_tready"
        d.m_axis_tready.value = m_ready
        await Timer(1, unit="ns")
        assert self.viol() == 0, f"clock {self.clk_n}: an AXI4-Stream rule monitor fired: {self.viol():#x}"
        e_sr, e_mv, e_md = self.model.signals(bool(m_ready))
        assert bool(s_ready) == e_sr, f"clock {self.clk_n}: s_ready {s_ready}, model {int(e_sr)}"
        assert bool(m_valid) == e_mv, f"clock {self.clk_n}: m_valid {m_valid}, model {int(e_mv)}"
        if m_valid:
            assert m_data == e_md, f"clock {self.clk_n}: m_data {m_data:#x}, model {e_md:#x}"
        acc = bool(s_valid and s_ready)
        out = bool(m_valid and m_ready)
        if acc:
            self.accepted.append(s_data)
        if out:
            self.delivered.append(m_data)
            assert len(self.delivered) <= len(self.accepted), "a beat left that was never accepted"
        self.model.clock(bool(s_valid), s_data, bool(m_ready))
        self.clk_n += 1
        await RisingEdge(d.aclk)
        await Timer(1, unit="ns")
        return acc, out


class Source:
    def __init__(self, rng, mask, p):
        self.rng, self.mask, self.p = rng, mask, p
        self.valid, self.data = 0, 0

    def drive(self):
        if not self.valid and self.rng.random() < self.p:
            self.valid, self.data = 1, self.rng.getrandbits(64) & self.mask
        return self.valid, self.data

    def done(self, acc):
        if acc:
            self.valid = 0


PROFILES = [(1.0, 1.0), (1.0, 0.5), (0.5, 1.0), (0.5, 0.5), (0.9, 0.1), (0.1, 0.9), (1.0, 0.02)]


@cocotb.test()
async def random_traffic(dut):
    b = Bench(dut)
    await b.start()
    rng = random.Random(SEED + 1000 * b.c + 100 * b.lf + 10 * b.lb + b.w)
    src = Source(rng, b.mask, 1.0)
    for pv, pr in PROFILES:
        src.p = pv
        burst = 0
        for t in range(CLOCKS // len(PROFILES)):
            if burst == 0 and rng.random() < 0.02:
                burst = rng.randrange(3, 60)
            mr = 0 if burst else int(rng.random() < pr)
            burst = max(0, burst - 1)
            v, dat = src.drive()
            acc, _ = await b.tick(v, dat, mr)
            src.done(acc)
            assert b.delivered == b.accepted[:len(b.delivered)], "beats lost, repeated or reordered"
            if rng.random() < 0.002:
                await b.reset(rng.randrange(1, 4))
                src = Source(rng, b.mask, pv)
    for _ in range(4 * (b.lf + b.lb + b.c) + 8):
        acc, _ = await b.tick(src.valid, src.data, 1)
        src.done(acc)
    assert b.delivered == b.accepted, f"{len(b.accepted)} accepted, {len(b.delivered)} delivered after the drain"
    dut._log.info("random_traffic ok: %d clocks", b.clk_n)


@cocotb.test()
async def measure(dut):
    b = Bench(dut)
    await b.start()
    d = dut
    res = {"W": b.w, "CREDITS": b.c, "LF": b.lf, "LB": b.lb}
    await b.tick(0, 0, 1)
    await b.tick(0, 0, 1)
    # latency: one beat into the empty channel, sink ready
    lat = None
    for t in range(4 * (b.lf + 3)):
        v = 1 if t == 0 else 0
        d.s_axis_tvalid.value, d.m_axis_tready.value = v, 1
        b.put_data(0x35 & b.mask)
        await Timer(1, unit="ns")
        if int(d.m_axis_tvalid.value) and lat is None:
            lat = t
        await RisingEdge(d.aclk)
        await Timer(1, unit="ns")
    res["latency"] = lat
    await b.reset(2)
    await b.tick(0, 0, 1)
    # throughput and the send pattern: always valid, always ready
    n = 40 + 20 * (b.lf + b.lb + 2) + 400
    sends = []
    k = 0
    for t in range(n):
        acc, _ = await b.tick(1, (k + 1) & b.mask, 1)
        if acc:
            k += 1
            sends.append(t)
    while not acc:                                        # the beat on offer stays on offer until it is taken
        acc, _ = await b.tick(1, (k + 1) & b.mask, 1)
        if acc:
            k += 1
    steady = [s for s in sends if s >= 100]
    span = n - 100
    res["throughput_accepted_per_clock"] = len(steady) / span
    res["window_clocks"] = span
    res["first_sends"] = sends[: b.c + 3]
    # credit round trip: clock distance from the first send to the send of the (CREDITS+1)th beat (with CREDITS below
    # the round trip this is the round trip; at or above it, it is CREDITS, the sender never ran out)
    res["send_gap_after_credits"] = sends[b.c] - sends[0]
    # a clean drain and capacity: sink stopped
    for _ in range(4 * (b.lf + b.lb + b.c) + 8):
        await b.tick(0, 0, 1)
    await b.reset(2)
    await b.tick(0, 0, 0)
    k = 0
    for t in range(4 * (b.lf + b.lb + b.c) + 16):
        acc, _ = await b.tick(1, (k + 1) & b.mask, 0)
        k += int(acc)
    res["capacity_beats"] = k
    out_path = os.environ.get("CREDIT_OUT")
    if out_path:
        with open(out_path, "a") as f:
            f.write(json.dumps(res) + "\n")
    dut._log.info("measure: %s", res)
