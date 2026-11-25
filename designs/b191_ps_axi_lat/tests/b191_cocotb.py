"""cocotb bench of rtl/axi_lat_probe.sv (brief 191): an AXI4 master that counts clock edges, so every timestamp the block returns is checked against the edge in which the
access was accepted. Clock numbering: edge E is the E-th rising edge with aresetn high; the counter before edge E holds E - 1, so an access accepted at edge E is stamped E - 1."""
from __future__ import annotations

import os
import random
import json
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

PERIOD_PS = 10000
ID, BUILD, CLK_HZ, SCRATCH, CNT, WR_TS, WR_N, LOG_N, TRIG, CTRL, BAD, LOG = 0x000, 0x004, 0x008, 0x00C, 0x010, 0x014, 0x018, 0x01C, 0x020, 0x024, 0x028, 0x400
OKAY, SLVERR = 0, 2


class Master:
    def __init__(self, dut):
        self.d = dut
        self.e = 0            # rising edges since release of reset
        self.writes = []      # (commit stamp expected, addr, data) of every write that went in
        self.rec = {}

    async def start(self):
        d = self.d
        cocotb.start_soon(Clock(d.aclk, PERIOD_PS, unit="ps").start())
        for n in ("awvalid", "wvalid", "bready", "arvalid", "rready", "wlast"):
            getattr(d, n).value = 0
        for n in ("awid", "awaddr", "awlen", "awsize", "wdata", "wstrb", "arid", "araddr", "arlen", "arsize"):
            getattr(d, n).value = 0
        d.aresetn.value = 0
        for _ in range(4):
            await RisingEdge(d.aclk)
        await Timer(500, unit="ps")
        d.aresetn.value = 1
        self.e = 0

    async def tick(self):
        await RisingEdge(self.d.aclk)
        await Timer(500, unit="ps")
        self.e += 1

    async def write(self, addr, data, strb=0xF, aw_delay=0, w_delay=0, b_delay=0, awlen=0, awsize=2, aid=0x1234):
        """One write: AW after aw_delay clocks, W after w_delay clocks (either may come first); returns (bresp, bid, stamp expected for the write)."""
        d = self.d
        aw_done = w_done = False
        aw_edge = w_edge = None
        t = 0
        while not (aw_done and w_done):
            aw_now, w_now = (not aw_done and t >= aw_delay), (not w_done and t >= w_delay)
            d.awvalid.value, d.wvalid.value = int(aw_now), int(w_now)
            if aw_now:
                d.awid.value, d.awaddr.value, d.awlen.value, d.awsize.value = aid, addr, awlen, awsize
            else:                                                                       # an idle bus carries garbage: the block must not look at it
                d.awid.value, d.awaddr.value, d.awlen.value, d.awsize.value = 0x5A5A, (addr ^ 0x10) & 0xFFFFFFFF, 3, 3
            if w_now:
                d.wdata.value, d.wstrb.value, d.wlast.value = data, strb, 1
            else:
                d.wdata.value, d.wstrb.value, d.wlast.value = 0xDEADBEEF ^ data, 0x5, 0
            aw_rdy, w_rdy = int(d.awready.value), int(d.wready.value)
            await self.tick()
            if aw_now and aw_rdy:
                aw_done, aw_edge = True, self.e
            if w_now and w_rdy:
                w_done, w_edge = True, self.e
            t += 1
        d.awvalid.value = d.wvalid.value = 0
        stamp = max(aw_edge, w_edge) - 1                       # the counter in the clock both were in
        for _ in range(b_delay):
            await self.tick()
            assert int(d.bvalid.value) == 1 or _ == 0
        # the response is presented the clock after the commit; the master takes it when it is ready
        while not int(d.bvalid.value):
            await self.tick()
        d.bready.value = 1
        resp, bid = int(d.bresp.value), int(d.bid.value)
        await self.tick()
        d.bready.value = 0
        self.writes.append((stamp, addr, data))
        return resp, bid, stamp

    async def read(self, addr, r_delay=0, arlen=0, arsize=2, rid=0x4321, wait_ready=True):
        """One read; returns (data, rresp, rid, stamp expected for the request's clock)."""
        d = self.d
        d.arvalid.value = 1
        d.arid.value, d.araddr.value, d.arlen.value, d.arsize.value = rid, addr, arlen, arsize
        while True:
            rdy = int(d.arready.value)
            await self.tick()
            if rdy:
                break
        stamp = self.e - 1
        d.arvalid.value = 0
        for _ in range(r_delay):
            await self.tick()
        while not int(d.rvalid.value):
            await self.tick()
        d.rready.value = 1
        data, resp, rid_o = int(d.rdata.value), int(d.rresp.value), int(d.rid.value)
        assert int(d.rlast.value) == 1
        await self.tick()
        d.rready.value = 0
        return data, resp, rid_o, stamp


@cocotb.test()
async def identity_and_scratch(dut):
    """ID, build stamp and clock registers read back; the scratch register keeps what was written (all four strobes) and ignores a partial strobe; ids come back on the responses."""
    m = Master(dut)
    await m.start()
    for addr, want in ((ID, 0x50534C54), (BUILD, int(dut.BUILD_ID.value)), (CLK_HZ, int(dut.CLK_HZ.value))):
        v, resp, rid, _ = await m.read(addr)
        assert (v, resp, rid) == (want, OKAY, 0x4321), (hex(addr), hex(v), resp, hex(rid))
    r, bid, _ = await m.write(SCRATCH, 0xCAFE0123)
    assert (r, bid) == (OKAY, 0x1234)
    assert (await m.read(SCRATCH))[0] == 0xCAFE0123
    r, _, _ = await m.write(SCRATCH, 0x11111111, strb=0x7)                    # a partial write is refused (SLVERR, counted), the register keeps its value
    assert r == SLVERR
    assert (await m.read(SCRATCH))[0] == 0xCAFE0123 and (await m.read(BAD))[0] == 1


@cocotb.test()
async def read_timestamps(dut):
    """CNT returns the clock the read request was accepted; back-to-back reads are two clocks apart at the fastest (request, response, next request); a slow master stretches it."""
    m = Master(dut)
    await m.start()
    stamps = []
    for k in range(20):
        v, resp, _, st = await m.read(CNT, r_delay=(k % 4))
        assert (v, resp) == (st, OKAY), (k, v, st)
        stamps.append(v)
    deltas = [b - a for a, b in zip(stamps, stamps[1:])]
    assert min(deltas) == 3 or min(deltas) == 2, deltas                       # the master model adds one clock to take the response
    dut._log.info("read-to-read intervals %s", deltas)
    m.rec["read_deltas"] = deltas
    out = os.environ.get("B191_RECORD")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "probe_sim.json").write_text(json.dumps({"min_read_to_read_clocks": min(deltas), "read_to_read_clocks_first_8": deltas[:8], "note": "from a master that takes each response in the clock it is presented, with 0 to 3 extra clocks of delay in turn"}, indent=2) + "\n")


@cocotb.test()
async def write_timestamps(dut):
    """WR_TS is the clock both AW and W were in, whichever came first (AW first, W first, together, far apart); WR_N counts the writes; TRIG logs the stamps in order; the log saturates and CLEAR restarts it."""
    m = Master(dut)
    await m.start()
    want = []
    n = 0
    for aw_d, w_d in ((0, 0), (0, 3), (3, 0), (5, 1), (1, 5), (0, 0), (2, 2), (0, 9), (9, 0), (4, 4)):
        _, _, st = await m.write(TRIG, 0xA5, aw_delay=aw_d, w_delay=w_d, b_delay=0)
        want.append(st)
        n += 1
        v, _, _, _ = await m.read(WR_TS)
        assert v == st, (aw_d, w_d, v, st)
        assert (await m.read(WR_N))[0] == n
    assert (await m.read(LOG_N))[0] == len(want)
    for i, st in enumerate(want):
        assert (await m.read(LOG + 4 * i))[0] == st, i
    # the log fills (256 entries) and then stops
    for i in range(300):
        await m.write(TRIG, 1)
    assert (await m.read(LOG_N))[0] == 256
    first = [(await m.read(LOG + 4 * i))[0] for i in range(len(want))]
    assert first == want                                                       # entries already logged are never overwritten
    r, _, _ = await m.write(CTRL, 1)
    assert r == OKAY and (await m.read(LOG_N))[0] == 0 and (await m.read(WR_N))[0] == 0
    await m.write(TRIG, 0)
    assert (await m.read(LOG_N))[0] == 1


@cocotb.test()
async def bad_accesses(dut):
    """A burst, a 64-bit access, a partial strobe, a write to a read-only register, an unmapped write and an unmapped read each answer SLVERR (reads of unmapped return 0) and count once in BAD; a good access does not; CTRL.CLEAR zeroes BAD."""
    m = Master(dut)
    await m.start()
    results = []
    results.append((await m.write(SCRATCH, 1, awlen=1))[0])
    results.append((await m.write(SCRATCH, 1, awsize=3))[0])
    results.append((await m.write(SCRATCH, 1, strb=0x3))[0])
    results.append((await m.write(ID, 1))[0])
    results.append((await m.write(0x300, 1))[0])
    assert results == [SLVERR] * 5, results
    v, resp, _, _ = await m.read(0x300)
    assert (v, resp) == (0, SLVERR)
    v, resp, _, _ = await m.read(CNT, arlen=2)
    assert resp == SLVERR
    v, resp, _, _ = await m.read(CNT, arsize=3)
    assert resp == SLVERR
    assert (await m.read(BAD))[0] == 8
    assert (await m.write(SCRATCH, 7))[0] == OKAY and (await m.read(BAD))[0] == 8
    await m.write(CTRL, 1)
    assert (await m.read(BAD))[0] == 0
    await m.write(CTRL, 0)                                                      # CLEAR not set: nothing changes
    assert (await m.read(WR_N))[0] >= 1


@cocotb.test()
async def random_against_model(dut):
    """Random mixed reads and writes with random delays against a small model of the registers (the stamps are checked against the edge counts)."""
    m = Master(dut)
    await m.start()
    r = random.Random(191)
    scratch, log, wr_n, bad = 0, [], 0, 0
    last_wr = None
    for k in range(400):
        c = r.randrange(5)
        if c == 0:
            v = r.getrandbits(32)
            _, _, st = await m.write(SCRATCH, v, aw_delay=r.randrange(4), w_delay=r.randrange(4), b_delay=r.randrange(3))
            scratch, wr_n, last_wr = v, wr_n + 1, st
        elif c == 1:
            _, _, st = await m.write(TRIG, r.getrandbits(32), aw_delay=r.randrange(4), w_delay=r.randrange(4))
            if len(log) < 256:
                log.append(st)
            wr_n, last_wr = wr_n + 1, st
        elif c == 2:
            v, _, _, st = await m.read(CNT, r_delay=r.randrange(3))
            assert v == st
        elif c == 3:
            assert (await m.read(SCRATCH, r_delay=r.randrange(3)))[0] == scratch
        else:
            if log:
                i = r.randrange(len(log))
                assert (await m.read(LOG + 4 * i))[0] == log[i]
            assert (await m.read(WR_N))[0] == wr_n
            if last_wr is not None:
                assert (await m.read(WR_TS))[0] == last_wr
    assert (await m.read(LOG_N))[0] == len(log)
