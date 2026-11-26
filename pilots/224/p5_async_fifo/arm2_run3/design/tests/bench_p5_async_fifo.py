import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import RisingEdge, Timer  # noqa: E402

ID = 546635777
CTRL, SNAP = 0x10, 0x30
W, R, E, OVF, UNF, STALL, OCC = 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x2C


def _h(dut, *names):
    for n in names:
        if hasattr(dut, n):
            return getattr(dut, n)
    return None


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.clk = _h(dut, "clk_25", "clk")
        self.gt = _h(dut, "gt_refclk", "gt_clk", "clk_gt", "gtclk", "rd_clk", "clk_rd")
        self.rst = _h(dut, "rst", "reset", "rst_in")
        self.m = model.Model()

    async def start(self):
        d = self.dut
        cocotb.start_soon(Clock(self.clk, 40, unit="ns").start())
        if self.gt is not None:
            cocotb.start_soon(Clock(self.gt, 6400, unit="ps").start())
        d.h_we.value = 0
        d.h_re.value = 0
        d.h_addr.value = 0
        d.h_wdata.value = 0
        if self.rst is not None:
            self.rst.value = 1
            for _ in range(8):
                await RisingEdge(self.clk)
            self.rst.value = 0
        for _ in range(8):
            await RisingEdge(self.clk)
        self.m.reset()

    async def cyc(self, n=1):
        for _ in range(n):
            await RisingEdge(self.clk)
            self.m.step()

    async def wr(self, addr, val):
        d = self.dut
        d.h_addr.value = addr
        d.h_wdata.value = val
        d.h_we.value = 1
        await RisingEdge(self.clk)
        self.m.step({"h_we": 1, "h_addr": addr, "h_wdata": val})
        d.h_we.value = 0
        await self.cyc(1)

    async def rd(self, addr):
        d = self.dut
        d.h_addr.value = addr
        d.h_re.value = 1
        await RisingEdge(self.clk)
        self.m.step({"h_re": 1, "h_addr": addr})
        d.h_re.value = 0
        await self.cyc(2)
        await Timer(1, unit="ns")
        return int(d.h_rdata.value)

    async def snap(self):
        await self.wr(SNAP, 1)
        await self.cyc(80)
        return [await self.rd(a) for a in (W, R, E, OVF, UNF, STALL, OCC)]

    async def stop_and_drain(self, n=1500):
        await self.wr(CTRL, 0 | (self.slow << 1 if hasattr(self, "slow") else 0))
        await self.cyc(n)


async def setup(dut):
    b = Bench(dut)
    await b.start()
    return b


# req: REQ-01, REQ-32, REQ-26, REQ-24
@cocotb.test()
async def test_reset_values(dut):
    b = await setup(dut)
    assert await b.rd(0x00) == ID
    assert await b.rd(0x08) == 0
    assert await b.rd(CTRL) == 0
    for a in (W, R, E, OVF, UNF, STALL, OCC, SNAP):
        assert await b.rd(a) == 0, hex(a)
    assert int(dut.sfp_tx_disable.value) == 1
    assert int(dut.led.value) == 0


# req: REQ-03, REQ-33, REQ-06
@cocotb.test()
async def test_scratch_and_hold(dut):
    b = await setup(dut)
    for v in (0xA5A5A5A5, 0xFFFFFFFF, 0, 0x12345678, 1):
        await b.wr(0x08, v)
        assert await b.rd(0x08) == v
        assert b.m.read_reg(8) == v
    await b.wr(0x08, 0xCAFEF00D)
    d = dut
    d.h_addr.value = 0x08
    d.h_re.value = 1
    await RisingEdge(b.clk)
    d.h_re.value = 0
    d.h_addr.value = 0x00  # address change without h_re must not alter output
    await RisingEdge(b.clk)
    await RisingEdge(b.clk)
    await Timer(1, unit="ns")
    for _ in range(6):
        assert int(d.h_rdata.value) == 0xCAFEF00D
        await RisingEdge(b.clk)
        await Timer(1, unit="ns")
    # ID is read-only
    await b.wr(0x00, 0x1234)
    assert await b.rd(0x00) == ID
    await b.wr(0x04, 0x1234)
    assert await b.rd(0x04) == await b.rd(0x04)


# req: REQ-04, REQ-05
@cocotb.test()
async def test_unmapped(dut):
    b = await setup(dut)
    await b.wr(0x08, 0x55555555)
    await b.wr(CTRL, 0)
    for a in (0x0C, 0x34, 0x38, 0x40, 0x100, 0x7FC, 0xFFC, 0x018 + 0x400 - 0x400 + 0x80):
        await b.wr(a, 0xFFFFFFFF)
        assert await b.rd(a) == 0, hex(a)
    assert await b.rd(0x08) == 0x55555555
    assert await b.rd(CTRL) == 0
    assert await b.rd(0x00) == ID
    assert await b.rd(OCC) == 0
    assert int(dut.led.value) == 0


async def run_stream(b, cycles, slow=0):
    await b.wr(CTRL, 1 | (slow << 1))
    await b.cyc(cycles)
    await b.wr(CTRL, slow << 1)
    await b.cyc(1500 if not slow else 12000)


# req: REQ-08, REQ-09, REQ-10, REQ-07, REQ-12, REQ-13, REQ-15, REQ-20
@cocotb.test()
async def test_stream_fast(dut):
    b = await setup(dut)
    n = 300
    await b.wr(CTRL, 1)
    assert int(dut.led.value) & 1 == 1
    await b.cyc(n)
    await b.wr(CTRL, 0)
    await b.cyc(1500)
    w, r, e, ovf, unf, stall, occ = await b.snap()
    mw = b.m.snap
    assert e == 0 and ovf == 0 and unf == 0 and stall == 0
    assert w == r, (w, r)
    # model comparison: writer count (model snapshot taken at its own timing)
    assert abs(w - n) <= 4, w
    assert abs(w - b.m.cnt[0]) <= 2, (w, b.m.cnt[0])
    assert 1 <= occ <= 512
    assert abs(occ - b.m.cnt[6]) <= 4, (occ, b.m.cnt[6])
    assert int(dut.led.value) == 0


# req: REQ-14, REQ-16, REQ-17, REQ-12, REQ-13, REQ-15, REQ-07, REQ-10
@cocotb.test()
async def test_slow_read_fills(dut):
    b = await setup(dut)
    await b.wr(CTRL, 3)
    await b.cyc(4500)
    w1, r1, e1, o1, u1, s1, occ1 = await b.snap()
    await b.wr(CTRL, 0b10)  # stop writer, keep slow
    await b.cyc(14000)
    w, r, e, ovf, unf, stall, occ = await b.snap()
    assert stall > 0 and s1 > 0
    assert occ == 512 and occ1 == 512
    assert e == 0 and ovf == 0 and unf == 0
    assert w == r
    assert stall > 100, stall
    # read rate bound: 4500 clk_25 cycles = 28125 gt cycles -> at most 1 per 8
    assert r1 <= (4600 * 40000 // 6400) // 8 + 3, r1
    assert r1 >= 512, r1
    # writes = reads + fill, stalls account for all other cycles
    assert w >= 512 + 100, w
    assert int(dut.led.value) == 0


# req: REQ-16
@cocotb.test()
async def test_slow_read_rate(dut):
    b = await setup(dut)
    await b.wr(CTRL, 3)
    await b.cyc(3000)  # fifo has filled by now
    a = await b.snap()
    await b.cyc(1000)
    c = await b.snap()
    gt_cycles = 1100 * 40000 / 6400
    d = c[1] - a[1]
    assert d <= (gt_cycles + 40 * 6.25) / 8 + 2, d
    assert d >= gt_cycles / 8 - 4, d
    # while stalled, write rate equals read rate
    assert c[0] - a[0] == d or abs((c[0] - a[0]) - d) <= 2


# req: REQ-18, REQ-19, REQ-34, REQ-24
@cocotb.test()
async def test_inject(dut):
    b = await setup(dut)
    await b.wr(CTRL, 1)
    await b.cyc(50)
    await b.wr(CTRL, 1 | 8)
    assert (await b.rd(CTRL)) == 1  # bit 3 self-cleared
    await b.cyc(400)
    await b.wr(CTRL, 0)
    await b.cyc(1500)
    w, r, e, ovf, unf, stall, occ = await b.snap()
    assert e == 1, e
    assert w == r and ovf == 0 and unf == 0
    assert int(dut.led.value) == 2
    # inject again: exactly one more
    await b.wr(CTRL, 1 | 8)
    await b.cyc(300)
    await b.wr(CTRL, 0)
    await b.cyc(1500)
    s = await b.snap()
    assert s[2] == 2, s
    assert s[0] == s[1]


# req: REQ-20
@cocotb.test()
async def test_snapshot_coherent(dut):
    b = await setup(dut)
    await b.wr(CTRL, 1)
    await b.cyc(200)
    await b.wr(SNAP, 0xDEAD)
    await b.cyc(80)
    a = [await b.rd(x) for x in (W, R, E, OVF, UNF, STALL, OCC)]
    await b.cyc(200)
    a2 = [await b.rd(x) for x in (W, R, E, OVF, UNF, STALL, OCC)]
    assert a == a2  # frozen until the next SNAPSHOT
    assert a[0] > 0 and a[1] > 0
    assert a[0] >= a[1]
    assert await b.rd(SNAP) == 0
    await b.cyc(100)
    s = await b.snap()
    assert s[0] > a[0] and s[1] > a[1]
    await b.wr(CTRL, 0)


# req: REQ-22, REQ-37, REQ-23, REQ-24
@cocotb.test()
async def test_clear(dut):
    b = await setup(dut)
    await b.wr(CTRL, 1)
    await b.cyc(500)
    # CLEAR while RUN=1 has no effect
    pre = await b.snap()
    await b.wr(CTRL, 1 | 4)
    assert (await b.rd(CTRL)) == 1
    await b.cyc(100)
    post = await b.snap()
    assert post[0] > pre[0] and post[1] >= pre[1]
    await b.wr(CTRL, 0)
    await b.cyc(1500)
    s = await b.snap()
    assert s[0] == s[1] and s[0] > 0
    # CLEAR with RUN=0
    await b.wr(CTRL, 4)
    assert (await b.rd(CTRL)) == 0
    z = await b.snap()
    assert z == [0] * 7, z
    # restart from the seed: a new run must see zero errors, even after a stop
    # at an odd place in the sequence
    await b.wr(CTRL, 1)
    await b.cyc(333)
    await b.wr(CTRL, 0)
    await b.cyc(1500)
    s = await b.snap()
    assert s[2] == 0 and s[0] == s[1] and s[0] > 0
    await b.wr(CTRL, 4)
    await b.wr(CTRL, 1)
    await b.cyc(77)
    await b.wr(CTRL, 0)
    await b.cyc(1500)
    s = await b.snap()
    assert s[2] == 0 and s[0] == s[1] and 60 < s[0] < 90, s
    # stop and resume without CLEAR keeps the sequences continuous
    await b.wr(CTRL, 1)
    await b.cyc(100)
    await b.wr(CTRL, 0)
    await b.cyc(1500)
    s = await b.snap()
    assert s[2] == 0 and s[0] == s[1]


# req: REQ-24
@cocotb.test()
async def test_ctrl_readback(dut):
    b = await setup(dut)
    for v in (0x2, 0xA, 0x2, 0x0, 0x6):
        await b.wr(CTRL, v)
        assert await b.rd(CTRL) == (v & 3), v
        assert await b.rd(CTRL) == b.m.read_reg(CTRL)
    await b.wr(CTRL, 0)


# req: REQ-21, REQ-35
@cocotb.test()
async def test_counter_width(dut):
    # 32-bit counters: count past 16 bits (a full 2^32 wrap cannot be simulated)
    b = await setup(dut)
    await b.wr(CTRL, 1)
    await b.cyc(70000)
    await b.wr(CTRL, 0)
    await b.cyc(1500)
    s = await b.snap()
    assert s[0] > 65536 and s[0] == s[1], s
    assert s[2] == 0 and s[3] == 0 and s[4] == 0 and s[5] == 0


# req: REQ-08, REQ-09, REQ-10, REQ-12, REQ-13, REQ-14, REQ-15, REQ-16, REQ-18, REQ-20, REQ-22
@cocotb.test()
async def test_random_traffic(dut):
    b = await setup(dut)
    rng = random.Random(cocotb.RANDOM_SEED)
    slow = 0
    exp_errs = 0
    for _ in range(8):
        slow = rng.choice([0, 1])
        inj = rng.random() < 0.5
        await b.wr(CTRL, 1 | (slow << 1))
        await b.cyc(rng.randint(50, 800 if not slow else 3000))
        if inj:
            await b.wr(CTRL, 1 | (slow << 1) | 8)
            exp_errs += 1
        await b.cyc(rng.randint(20, 600))
        await b.wr(CTRL, slow << 1)
        await b.cyc(5000 if slow else 1500)
        if rng.random() < 0.3:
            await b.wr(SNAP, 1)
            await b.cyc(80)
        s = await b.snap()
        assert s[0] == s[1], s
        assert s[2] == exp_errs, (s, exp_errs)
        assert s[3] == 0 and s[4] == 0
        assert s[6] <= 512
        if slow == 0:
            assert s[5] == 0 or s[6] == 512
        if rng.random() < 0.3:
            await b.wr(CTRL, 4)
            s = await b.snap()
            assert s == [0] * 7
            exp_errs = 0
        await b.wr(0x08, rng.getrandbits(32))
        assert await b.rd(0x08) == b.m.scratch
        assert int(dut.sfp_tx_disable.value) == 1
