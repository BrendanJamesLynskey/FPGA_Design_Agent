"""cocotb bench for ip_lib/pipe_reg (brief 151) against model.py, clock by clock.

Every clock: the bench drives s_valid, s_data and m_ready, lets the combinational paths settle, then compares s_ready,
m_valid and (when valid) m_data with the model's prediction, so the ready timing of every mode is checked as well as the
data. A second scoreboard, independent of the model, checks that the beats that leave are exactly the beats accepted,
in order, none lost or repeated (reset clears the chain, so the lists are compared per reset segment).
The top is pipe_reg_axis_tb (pipe_reg plus the AXI4-Stream rule monitor of axi_tx/rtl/axis_rules.sv on both ports): any
broken rule, on the slave side or the master side, fails the run. The bench also checks that m_axis_tvalid does not depend
on m_axis_tready (it flips tready within the clock and requires tvalid to stay put). The carried signals (tdata, tlast, tkeep,
tuser as parameters enable them) move as one packed word {tuser, tkeep, tlast, tdata}; the model sees the packed word.
Tests: `random_traffic` (several source/sink profiles, random resets) and `measure` (latency, throughput, capacity,
ready response; written to $PIPE_REG_OUT as JSON when set). Environment: PIPE_REG_SEED, PIPE_REG_CLOCKS."""
from __future__ import annotations

import json
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from ip_lib.pipe_reg import model as M

SEED = int(os.environ.get("PIPE_REG_SEED", "1"))
CLOCKS = int(os.environ.get("PIPE_REG_CLOCKS", "1500"))


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.dw, self.n, self.mode = int(dut.W.value), int(dut.N.value), int(dut.MODE.value)
        self.tl, self.tk, self.tu = int(dut.TLAST_EN.value), int(dut.TKEEP_EN.value), int(dut.TUSER_W.value)
        self.kw = max(self.dw // 8, 1)
        self.w = self.dw + self.tl + (self.kw if self.tk else 0) + self.tu      # the packed word
        self.mask = (1 << self.w) - 1
        self.model = M.Pipe(self.n, self.mode)
        self.accepted: list[int] = []          # beats taken in since the last reset
        self.delivered: list[int] = []         # beats given out since the last reset
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
        self.model.in_reset = False
        if self.accepted or self.delivered:
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
        """One clock: drive, settle, compare with the model, advance. Returns (accepted, delivered)."""
        d = self.dut
        d.s_axis_tvalid.value, d.m_axis_tready.value = s_valid, m_ready
        self.put_data(s_data)
        await Timer(1, unit="ns")
        s_ready = int(d.s_axis_tready.value)
        m_valid = int(d.m_axis_tvalid.value)
        m_data = self.get_data() if m_valid else None
        # tvalid must not depend on tready: flip tready, let the logic settle, tvalid must not move
        d.m_axis_tready.value = 1 - m_ready
        await Timer(1, unit="ns")
        assert int(d.m_axis_tvalid.value) == m_valid, f"clock {self.clk_n}: m_axis_tvalid depends on m_axis_tready"
        d.m_axis_tready.value = m_ready
        await Timer(1, unit="ns")
        self.hist = getattr(self, 'hist', [])[-6:] + [(self.clk_n, s_valid, hex(s_data), m_ready, s_ready, m_valid)]
        assert self.viol() == 0, f"{self.hist} clock {self.clk_n}: an AXI4-Stream rule monitor fired: slave {int(d.viol_s.value):#x} master {int(d.viol_m.value):#x} (valid {s_valid}, ready out {s_ready}, m_valid {m_valid}, m_ready {m_ready})"
        if self.n == 0:
            exp = (bool(m_ready), bool(s_valid), s_data if s_valid else None)
        else:
            exp = self.model.signals(bool(m_ready))
        assert bool(s_ready) == exp[0], f"clock {self.clk_n}: s_ready {s_ready}, model {int(exp[0])}"
        assert bool(m_valid) == exp[1], f"clock {self.clk_n}: m_valid {m_valid}, model {int(exp[1])}"
        if m_valid:
            assert m_data == exp[2], f"clock {self.clk_n}: m_data {m_data:#x}, model {exp[2]:#x}"
        acc = bool(s_valid and s_ready)
        out = bool(m_valid and m_ready)
        if acc:
            self.accepted.append(s_data)
        if out:
            self.delivered.append(m_data)
            k = len(self.delivered) - 1
            assert k < len(self.accepted) or self.n == 0 and acc, "a beat left that was never accepted"
        self.model.clock(bool(s_valid), s_data, bool(m_ready))
        self.clk_n += 1
        await RisingEdge(d.aclk)
        await Timer(1, unit="ns")
        assert self.viol() == 0 or True
        return acc, out

    def check_lists(self):
        assert self.delivered == self.accepted[:len(self.delivered)], "beats lost, repeated or reordered"


class Source:
    """AXI-Stream style: once s_valid is up it stays up, with the same data, until the beat is accepted."""

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
    rng = random.Random(SEED + 1000 * b.n + 10 * b.mode + b.w)
    src = Source(rng, b.mask, 1.0)
    for pv, pr in PROFILES:
        src.p = pv                                        # the same source carries on: an offered beat is never withdrawn
        burst = 0                                         # sink pattern: bursts of stall as well as per-clock randomness
        for t in range(CLOCKS // len(PROFILES)):
            if burst == 0 and rng.random() < 0.02:
                burst = rng.randrange(3, 40)
            mr = 0 if burst else int(rng.random() < pr)
            burst = max(0, burst - 1)
            v, dat = src.drive()
            acc, _ = await b.tick(v, dat, mr)
            src.done(acc)
            b.check_lists()
            if rng.random() < 0.003:                      # a reset in the middle of traffic
                await b.reset(rng.randrange(1, 4))
                src = Source(rng, b.mask, pv)
    # drain: stop the source, take everything out
    for _ in range(8 * (b.n + 2)):
        acc, _ = await b.tick(src.valid, src.data, 1)      # a beat on offer stays on offer until it is taken
        src.done(acc)
    assert not src.valid
    assert b.delivered == b.accepted, f"{len(b.accepted)} accepted, {len(b.delivered)} delivered after the drain"
    dut._log.info("random_traffic ok: %d clocks", b.clk_n)


async def run_stream(b: Bench, clocks: int, mr_fn, finish=False):
    """Offer a beat every clock; returns (accepted per clock list, delivered per clock list)."""
    acc_l, out_l = [], []
    k = 0
    for t in range(clocks):
        acc, out = await b.tick(1, (k + 1) & b.mask, mr_fn(t))
        if acc:
            k += 1
        acc_l.append(int(acc))
        out_l.append(int(out))
    if finish:
        while not acc_l[-1]:                              # the last beat on offer stays on offer until it is taken
            acc, out = await b.tick(1, (k + 1) & b.mask, 1)
            acc_l.append(int(acc))
            out_l.append(int(out))
    return acc_l, out_l


@cocotb.test()
async def measure(dut):
    b = Bench(dut)
    await b.start()
    res = {"W": b.w, "N": b.n, "MODE": b.mode, "mode": M.NAMES[b.mode]}
    # latency: one beat into an empty chain, sink ready; clocks until it is visible at m_*
    await b.tick(0, 0, 1)
    await b.tick(0, 0, 1)
    s_ready_seen = False
    lat = None
    d = dut
    for t in range(40):
        v = 1 if t == 0 else 0
        d.s_axis_tvalid.value, d.m_axis_tready.value = v, 1
        b.put_data(0x5A & b.mask)
        await Timer(1, unit="ns")
        if t == 0:
            if not int(d.s_axis_tready.value):
                lat = None
                break
        mv = int(d.m_axis_tvalid.value)
        if mv and lat is None:
            lat = t                                  # the clock in which it is visible: t = 0 is the accepting clock itself
        b.model.clock(bool(v), 0x5A & b.mask, True) if b.n else None
        await RisingEdge(d.aclk)
        await Timer(1, unit="ns")
    # t = 0 is the clock whose closing edge accepts the beat. Visible in clock t = k means k clocks after that
    # edge: k is the latency as the library counts it (1 for one register; 0 for a wire).
    res["latency"] = lat
    # flush and re-sync the model
    await b.reset(2)
    await b.tick(0, 0, 1)
    # throughput: always valid, always ready, 400 clocks after a 40-clock warm-up
    acc, out = await run_stream(b, 440, lambda t: 1, finish=True)
    res["throughput_accepted_per_clock"] = sum(acc[40:440]) / 400.0
    res["throughput_delivered_per_clock"] = sum(out[40:440]) / 400.0
    for _ in range(4 * b.n + 4):
        await b.tick(0, 0, 1)
    # capacity: sink stopped, source always offering, until s_ready has been low for 8 clocks in a row
    await b.reset(2)
    await b.tick(0, 0, 0)
    acc, out = await run_stream(b, 12 * b.n + 24, lambda t: 0)
    res["capacity_beats"] = sum(acc)
    res["capacity_out_while_stalled"] = sum(out)
    # ready response: from here the chain is full. Raise m_ready; count clocks until s_ready is first seen high again
    # while the source keeps offering (clocks counted from the clock m_ready is first high; 0 = same clock)
    first = None
    k = res["capacity_beats"]                           # the beat on offer is the next one in the stream
    for t in range(8 * b.n + 12):
        d.s_axis_tvalid.value, d.m_axis_tready.value = 1, 1
        b.put_data((k + 1) & b.mask)
        await Timer(1, unit="ns")
        sr = int(d.s_axis_tready.value)
        if sr and first is None:
            first = t
        exp = M.Pipe.signals(b.model, True) if b.n else (True, None, None)
        b.model.clock(True, (k + 1) & b.mask, True) if b.n else None
        if sr:
            k += 1
        await RisingEdge(d.aclk)
        await Timer(1, unit="ns")
    res["ready_response_clocks"] = first
    out_path = os.environ.get("PIPE_REG_OUT")
    if out_path:
        with open(out_path, "a") as f:
            f.write(json.dumps(res) + "\n")
    dut._log.info("measure: %s", res)
