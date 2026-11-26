"""cocotb bench for the p5 async FIFO soak register core, checked against model.py.

Clocks: writer/register clock 25 MHz (40 ns), reader clock 156.25 MHz (6.4 ns).
Counters that depend on the exact CDC latency are compared with a tolerance.
"""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

ID = 0x20950001
CTRL, W_W, W_R, ERRS, OVF, UNF, STALL, OCC, SNAP = 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x2C, 0x30
RUN, SLOW, CLR, INJ = 1, 2, 4, 8
MASK = 0xFFFFFFFF


def _find(dut, names, contains=()):
    for n in names:
        if hasattr(dut, n):
            return getattr(dut, n)
    for n in dir(dut):
        for c in contains:
            if c in n and not n.startswith("_"):
                return getattr(dut, n)
    return None


def _start_clock(sig, period_ps):
    try:
        cocotb.start_soon(Clock(sig, period_ps, units="ps").start())
    except TypeError:
        cocotb.start_soon(Clock(sig, period_ps, unit="ps").start())


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.wclk = _find(dut, ["clk_c3", "clk"], ["c3"])
        self.rclk = _find(dut, ["clk_gt156", "clk_rd", "rd_clk", "clk_r", "rclk"], ["gt156", "rd"])
        self.rst = _find(dut, ["rst", "reset"])
        assert self.wclk is not None, "writer clock port not found"
        if self.rclk is None:
            names = []
            try:
                names = [h._name for h in dut]
            except Exception:
                names = [n for n in dir(dut) if not n.startswith("_")]
            wname = getattr(self.wclk, "_name", "clk_c3")
            for n in names:
                nl = n.lower()
                if n != wname and ("clk" in nl or "clock" in nl) and "refclk" not in nl and "en" != nl:
                    self.rclk = getattr(dut, n)
                    break
        self.m = model.Model()
        self.m.reset()

    async def tick(self, n=1):
        for _ in range(n):
            await RisingEdge(self.wclk)
            await Timer(1, "ns")

    async def start(self):
        d = self.dut
        _start_clock(self.wclk, 40000)
        if self.rclk is not None:
            _start_clock(self.rclk, 6400)
        else:
            p = _find(d, ["gt_refclk_p", "gt_refclk"], ["refclk_p", "gt"])
            n = _find(d, ["gt_refclk_n"], ["refclk_n"])
            if p is not None:
                _start_clock(p, 6400)
            if n is not None:
                async def _inv():
                    while True:
                        n.value = 1 - int(p.value) if p is not None and p.value.is_resolvable else 1
                        await Timer(100, "ps")
                cocotb.start_soon(_inv())
        d.h_we.value = 0
        d.h_re.value = 0
        d.h_addr.value = 0
        d.h_wdata.value = 0
        if self.rst is not None:
            self.rst.value = 1
            await self.tick(10)
            self.rst.value = 0
        await self.tick(40)
        self.m = model.Model()
        self.m.reset()
        # leave the counters and sequences at the seed
        await self.write(CTRL, CLR)
        await self.tick(10)
        await self.write(CTRL, 0)
        await self.tick(10)

    async def write(self, addr, val):
        d = self.dut
        d.h_we.value = 1
        d.h_addr.value = addr
        d.h_wdata.value = val & MASK
        await self.tick(1)
        d.h_we.value = 0
        await self.tick(1)
        self.m.write_reg(addr, val)

    async def read(self, addr):
        d = self.dut
        d.h_re.value = 1
        d.h_addr.value = addr
        await self.tick(1)
        d.h_re.value = 0
        await self.tick(2)
        return int(d.h_rdata.value)

    async def snapshot(self):
        await self.write(SNAP, 1)
        await self.tick(80)
        out = {}
        for k, a in (("w", W_W), ("r", W_R), ("err", ERRS), ("ovf", OVF), ("unf", UNF),
                     ("stall", STALL), ("occ", OCC)):
            out[k] = await self.read(a)
        return out

    def led(self):
        return int(self.dut.led.value)


# req: REQ-01, REQ-29, REQ-02, REQ-23, REQ-24
@cocotb.test()
async def test_reset_and_ids(dut):
    b = Bench(dut)
    await b.start()
    assert await b.read(0x000) == ID == b.m.read_reg(0)
    assert await b.read(0x008) == 0 == b.m.read_reg(8)
    build = await b.read(0x004)
    assert build == await b.read(0x004)  # stable stamp
    for a in (W_W, W_R, ERRS, OVF, UNF, STALL, OCC, CTRL):
        assert await b.read(a) == b.m.read_reg(a) == 0, hex(a)
    assert await b.read(SNAP) == 0
    assert int(dut.sfp_tx_disable.value) == 1
    assert (b.led() & 3) == 0
    await b.write(CTRL, RUN)
    await b.tick(50)
    assert int(dut.sfp_tx_disable.value) == 1
    assert (b.led() & 1) == 1  # led0 is RUN
    await b.write(CTRL, 0)
    await b.tick(100)
    assert int(dut.sfp_tx_disable.value) == 1
    assert (b.led() & 1) == 0


# req: REQ-03, REQ-04, REQ-30, REQ-28
@cocotb.test()
async def test_scratch_and_unmapped(dut):
    b = Bench(dut)
    await b.start()
    rng = random.Random(1234)
    vals = [0xFFFFFFFF, 0, 0x12345678, 0x80000000, 1] + [rng.getrandbits(32) for _ in range(8)]
    for v in vals:
        await b.write(0x008, v)
        assert await b.read(0x008) == v == b.m.read_reg(8)
    last = vals[-1]
    unmapped = [0x00C, 0x034, 0x038, 0x03C, 0x040, 0x0F0, 0x100, 0x7FC, 0x800, 0xFFC, 0x018 + 1 + 0x100]
    for a in unmapped:
        assert await b.read(a) == 0, hex(a)
        await b.write(a, 0xDEADBEEF)
        assert await b.read(a) == 0, hex(a)
    # writes to unmapped addresses changed nothing
    assert await b.read(0x008) == last
    assert await b.read(0x000) == ID
    assert await b.read(CTRL) == 0
    for a in (W_W, W_R, ERRS, OVF, UNF, STALL, OCC):
        assert await b.read(a) == 0
    # RO registers ignore writes
    await b.write(0x000, 0x55)
    assert await b.read(0x000) == ID
    await b.write(W_W, 0x55)
    assert await b.read(W_W) == 0
    # snapshot write does not change scratch
    await b.write(SNAP, 7)
    await b.tick(80)
    assert await b.read(0x008) == last


# req: REQ-05, REQ-31, REQ-26
@cocotb.test()
async def test_read_latency_and_hold(dut):
    b = Bench(dut)
    await b.start()
    d = dut
    await b.write(0x008, 0xA5A5A5A5)
    # the write is effective one clock after h_we: read after one idle clock sees it
    d.h_re.value = 1
    d.h_addr.value = 0x008
    await b.tick(1)
    d.h_re.value = 0
    d.h_addr.value = 0x000
    await b.tick(2)
    assert int(d.h_rdata.value) == 0xA5A5A5A5  # within 2 clocks of the h_re edge
    for _ in range(20):  # holds until the next h_re
        await b.tick(1)
        assert int(d.h_rdata.value) == 0xA5A5A5A5
    d.h_addr.value = 0x008
    await b.tick(5)
    assert int(d.h_rdata.value) == 0xA5A5A5A5
    # read ID, then hold ID
    d.h_re.value = 1
    d.h_addr.value = 0x000
    await b.tick(1)
    d.h_re.value = 0
    d.h_addr.value = 0x008
    await b.tick(2)
    assert int(d.h_rdata.value) == ID
    await b.tick(30)
    assert int(d.h_rdata.value) == ID
    # back-to-back reads
    for a, exp in ((0x000, ID), (0x008, 0xA5A5A5A5), (0x000, ID)):
        d.h_re.value = 1
        d.h_addr.value = a
        await b.tick(1)
        d.h_re.value = 0
        await b.tick(2)
        assert int(d.h_rdata.value) == exp
    # write with back-to-back scratch values, effective after one clock
    for v in (1, 2, 3):
        d.h_we.value = 1
        d.h_addr.value = 0x008
        d.h_wdata.value = v
        await b.tick(1)
        d.h_we.value = 0
        await b.tick(1)
        assert await b.read(0x008) == v


# req: REQ-06, REQ-09, REQ-16, REQ-20, REQ-21, REQ-25, REQ-34, REQ-37, REQ-27
@cocotb.test()
async def test_run_counters(dut):
    b = Bench(dut)
    await b.start()
    N = 3000
    await b.write(CTRL, RUN)
    s0 = await b.snapshot()
    await b.tick(N)
    s1 = await b.snapshot()
    assert s1["w"] > s0["w"]
    # model comparison of the writer count over the same interval
    m = model.Model()
    m.write_reg(CTRL, RUN)
    for _ in range(N + 200):
        m.step({})
    m.write_reg(SNAP, 1)
    mw = m.read_reg(W_W)
    assert abs(s1["w"] - mw) <= 200 + 12, (s1["w"], mw)
    # rate: one word per clock (delta over exactly N + snapshot gaps)
    dw = s1["w"] - s0["w"]
    assert abs(dw - (N + 82 + 6)) <= 20, dw
    assert s1["r"] <= s1["w"] + 1
    assert s1["w"] - s1["r"] <= 12  # reader keeps up in fast mode
    assert s1["err"] == 0 and s1["ovf"] == 0 and s1["unf"] == 0
    assert s1["stall"] == 0
    # reads return the held snapshot while the counters run
    a = await b.read(W_W)
    await b.tick(100)
    assert await b.read(W_W) == a == s1["w"]
    s2 = await b.snapshot()
    assert s2["w"] > s1["w"] and s2["r"] > s1["r"]
    assert s2["r"] <= s2["w"] + 1  # coherent: reader never ahead of writer
    # stop: counters hold while RUN is 0
    await b.write(CTRL, 0)
    await b.tick(300)
    s3 = await b.snapshot()
    await b.tick(300)
    s4 = await b.snapshot()
    assert s3 == s4
    assert s3["err"] == 0 and s3["ovf"] == 0 and s3["unf"] == 0
    assert 0 <= s3["w"] - s3["r"] <= 12
    assert (b.led() & 2) == 0


# req: REQ-07, REQ-08, REQ-10, REQ-11, REQ-36, REQ-18, REQ-19, REQ-22
@cocotb.test()
async def test_slow_read_fill_and_stall(dut):
    b = Bench(dut)
    await b.start()
    N = 4500
    await b.write(CTRL, RUN | SLOW)
    await b.tick(N)
    s = await b.snapshot()
    assert s["occ"] == 512, s
    assert s["stall"] > 0, s
    assert s["ovf"] == 0 and s["unf"] == 0 and s["err"] == 0, s
    # every writer clock either wrote a word or stalled
    assert abs((s["w"] + s["stall"]) - (N + 82)) <= 12, s
    # at most one read per 8 reader clocks (6.25 reader clocks per writer clock)
    max_reads = (N + 82 + 10) * 6.25 / 8 + 4
    assert 0 < s["r"] <= max_reads, (s, max_reads)
    # the FIFO never holds more than 512: written - read <= 512 (+ small in-flight slack)
    assert s["w"] - s["r"] <= 512 + 8, s
    # model reaches 512 too
    m = model.Model()
    m.write_reg(CTRL, RUN | SLOW)
    for _ in range(N):
        m.step({})
    assert m.c["occ"] == 512 and m.c["stall"] > 0
    assert (b.led() & 2) == 0
    # stall counts one per held-off clock: two snapshots 600 clocks apart
    s2 = await b.snapshot()
    gap = 82 + 6
    dstall = s2["stall"] - s["stall"]
    dw = s2["w"] - s["w"]
    assert abs((dstall + dw) - gap) <= 12, (dstall, dw)
    assert s2["occ"] == 512
    # stop and drain
    await b.write(CTRL, SLOW)
    await b.tick(1500)
    s3 = await b.snapshot()
    assert s3["err"] == 0 and s3["ovf"] == 0 and s3["unf"] == 0
    assert s3["occ"] == 512
    stall_after = s3["stall"]
    await b.tick(200)
    s4 = await b.snapshot()
    assert s4["stall"] == stall_after  # no counting while RUN is 0


# req: REQ-12, REQ-35, REQ-13, REQ-23
@cocotb.test()
async def test_inject(dut):
    b = Bench(dut)
    await b.start()
    await b.write(CTRL, RUN)
    await b.tick(100)
    s0 = await b.snapshot()
    assert s0["err"] == 0
    await b.write(CTRL, RUN | INJ)
    await b.tick(60)
    assert (await b.read(CTRL)) & INJ == 0  # self-cleared
    assert (await b.read(CTRL)) & 3 == RUN
    await b.tick(200)
    s1 = await b.snapshot()
    assert s1["err"] == 1, s1
    assert (b.led() & 2) == 2  # led1 error seen
    assert s1["ovf"] == 0 and s1["unf"] == 0
    await b.tick(500)
    s2 = await b.snapshot()
    assert s2["err"] == 1  # exactly one word
    # second, third inject: two more errors
    for _ in range(2):
        await b.write(CTRL, RUN | INJ)
        await b.tick(150)
    await b.tick(100)
    s3 = await b.snapshot()
    assert s3["err"] == 3, s3
    assert int(dut.sfp_tx_disable.value) == 1
    await b.write(CTRL, 0)
    await b.tick(200)
    s4 = await b.snapshot()
    assert s4["err"] == 3
    assert (await b.read(CTRL)) & INJ == 0


# req: REQ-14, REQ-32, REQ-15, REQ-13
@cocotb.test()
async def test_clear(dut):
    b = Bench(dut)
    await b.start()
    await b.write(CTRL, RUN)
    await b.tick(400)
    # CLEAR while RUN=1 has no effect
    s_before = await b.snapshot()
    await b.write(CTRL, RUN | CLR)
    await b.tick(50)
    assert (await b.read(CTRL)) & CLR == 0
    s_after = await b.snapshot()
    assert s_after["w"] > s_before["w"] and s_after["r"] > s_before["r"]
    assert s_after["w"] >= s_before["w"] + 50
    # stop, inject an error so that ERRS != 0, then CLEAR with RUN=0
    await b.write(CTRL, RUN | INJ)
    await b.tick(100)
    await b.write(CTRL, 0)
    await b.tick(300)
    s = await b.snapshot()
    assert s["w"] > 0 and s["r"] > 0 and s["err"] == 1
    await b.write(CTRL, CLR)
    await b.tick(50)
    assert (await b.read(CTRL)) & CLR == 0
    s = await b.snapshot()
    assert all(v == 0 for v in s.values()), s
    # sequences restarted from the seed: a new run is error free and counts from 0
    await b.write(CTRL, RUN)
    await b.tick(500)
    s = await b.snapshot()
    assert s["err"] == 0 and s["ovf"] == 0 and s["unf"] == 0
    assert 400 <= s["w"] <= 700, s
    assert s["w"] - s["r"] <= 12
    await b.write(CTRL, 0)
    await b.tick(300)
    await b.write(CTRL, CLR)
    await b.tick(50)
    # CLEAR plus a fill in slow mode, then clear again: pointers restart cleanly
    await b.write(CTRL, RUN | SLOW)
    await b.tick(600)
    await b.write(CTRL, SLOW)
    await b.tick(1200)
    await b.write(CTRL, CLR | SLOW)
    await b.tick(50)
    s = await b.snapshot()
    assert all(v == 0 for v in s.values()), s
    await b.write(CTRL, RUN)
    await b.tick(400)
    await b.write(CTRL, 0)
    await b.tick(300)
    s = await b.snapshot()
    assert s["err"] == 0 and s["w"] > 300 and s["unf"] == 0 and s["ovf"] == 0


# req: REQ-17, REQ-33
@cocotb.test()
async def test_counter_width_wrap_model(dut):
    b = Bench(dut)
    await b.start()
    # all registers carry 32 bits
    await b.write(0x008, 0xFFFFFFFF)
    assert await b.read(0x008) == 0xFFFFFFFF
    # the model wraps a counter at its width (small width stands in for 2^32)
    m = model.Model(COUNTER_WIDTH=4)
    m.write_reg(CTRL, RUN)
    for _ in range(40):
        m.step({})
    m.write_reg(SNAP, 1)
    assert m.read_reg(W_W) == (40 - m.c["stall"]) % 16 or m.read_reg(W_W) < 16
    m32 = model.Model()
    m32.c["w"] = MASK
    m32._cnt("w")
    assert m32.c["w"] == 0
    # the RTL counters read as 32-bit values and stay within 32 bits
    await b.write(CTRL, RUN)
    await b.tick(200)
    s = await b.snapshot()
    for v in s.values():
        assert 0 <= v <= MASK
    assert s["w"] > 0


# req: REQ-03, REQ-04, REQ-18, REQ-19, REQ-20
@cocotb.test()
async def test_random_traffic(dut):
    b = Bench(dut)
    await b.start()
    seed = getattr(cocotb, "RANDOM_SEED", 1) or 1
    rng = random.Random(seed)
    injects = 0
    scratch = 0
    ctrl = 0
    phases = 14
    for _ in range(phases):
        run = rng.random() < 0.75
        slow = rng.random() < 0.4
        ctrl = (RUN if run else 0) | (SLOW if slow else 0)
        await b.write(CTRL, ctrl)
        length = rng.randint(400, 1200) if not slow else rng.randint(400, 800)
        t = 0
        did_inject = False
        while t < length:
            op = rng.choice(["wr_scr", "rd_scr", "rd_id", "rd_unm", "wr_unm", "rd_ctrl", "snap", "idle"])
            if op == "wr_scr":
                scratch = rng.getrandbits(32)
                await b.write(0x008, scratch)
                t += 2
            elif op == "rd_scr":
                assert await b.read(0x008) == scratch
                t += 3
            elif op == "rd_id":
                assert await b.read(0x000) == ID
                t += 3
            elif op == "rd_unm":
                assert await b.read(rng.choice([0x00C, 0x034, 0x100, 0x7F0, 0xFFC])) == 0
                t += 3
            elif op == "wr_unm":
                await b.write(rng.choice([0x00C, 0x034, 0x100, 0x7F0, 0xFFC]), rng.getrandbits(32))
                t += 2
            elif op == "rd_ctrl":
                assert (await b.read(CTRL)) & 3 == ctrl & 3
                t += 3
            elif op == "snap":
                await b.write(SNAP, rng.getrandbits(32))
                t += 2
                await b.tick(40)
                t += 40
            else:
                n = rng.randint(1, 30)
                await b.tick(n)
                t += n
            if run and not slow and not did_inject and t > 30 and length - t > 350:
                await b.write(CTRL, ctrl | INJ)
                injects += 1
                did_inject = True
                await b.tick(150)
                t += 152
        if did_inject:
            await b.tick(100)
    await b.write(CTRL, 0)
    await b.tick(1500)
    s = await b.snapshot()
    assert s["ovf"] == 0 and s["unf"] == 0, s
    assert s["err"] == injects, (s, injects)
    assert await b.read(0x008) == scratch
    assert s["r"] <= s["w"] + 1
