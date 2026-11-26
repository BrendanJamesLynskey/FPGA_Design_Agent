import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402
from model import Model  # noqa: E402

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import RisingEdge  # noqa: E402

ID = 0x20950001
CTRL, WW, WR, ERR, OVF, UNF, STALL, OCC, SNAP = 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x2C, 0x30
RUN, SLOW, CLEAR, INJECT = 1, 2, 4, 8

CLK_NAMES = ["clk25", "clk", "clk_w", "wclk", "clk_wr"]
GT_NAMES = ["gt_clk", "gt_refclk", "clk_gt", "gtclk", "rclk", "clk_r", "rd_clk", "clk_rd",
            "clk156", "clk_156", "gt_refclk_bufg", "refclk", "clk_gt156", "gt_clk156"]


class Bench:
    def __init__(self, dut):
        self.dut = dut
        names = [h._name for h in dut]
        self.names = names
        self.clk = next(n for n in CLK_NAMES if n in names)
        gt = [n for n in GT_NAMES if n in names]
        if not gt:
            gt = [n for n in names if "clk" in n.lower() and n != self.clk]
        self.gt = gt[0] if gt else None
        self.rsts = [n for n in names if n.lower().startswith("rst")]

    def sig(self, n):
        return getattr(self.dut, n)

    async def start(self):
        c = self.sig(self.clk)
        cocotb.start_soon(Clock(c, 40000, "ps").start())
        if self.gt:
            cocotb.start_soon(Clock(self.sig(self.gt), 6400, "ps").start())
        for n in ("h_we", "h_re", "h_addr", "h_wdata"):
            self.sig(n).value = 0
        for n in self.rsts:
            self.sig(n).value = 1
        for _ in range(20):
            await RisingEdge(c)
        for n in self.rsts:
            self.sig(n).value = 0
        for _ in range(8):
            await RisingEdge(c)

    async def cyc(self, n=1):
        c = self.sig(self.clk)
        for _ in range(n):
            await RisingEdge(c)

    async def write(self, addr, val):
        await self.cyc()
        self.dut.h_we.value = 1
        self.dut.h_addr.value = addr
        self.dut.h_wdata.value = val
        await self.cyc()
        self.dut.h_we.value = 0
        await self.cyc()

    async def read(self, addr):
        await self.cyc()
        self.dut.h_re.value = 1
        self.dut.h_addr.value = addr
        await self.cyc()
        self.dut.h_re.value = 0
        await self.cyc(2)
        return int(self.dut.h_rdata.value)

    async def snapshot(self):
        await self.write(SNAP, 1)
        await self.cyc(24)
        return [await self.read(a) for a in (WW, WR, ERR, OVF, UNF, STALL, OCC)]

    async def drain(self):
        """RUN=0, SLOW=0, wait for the reader to empty the FIFO."""
        await self.write(CTRL, 0)
        await self.cyc(900)


async def setup(dut):
    b = Bench(dut)
    await b.start()
    return b


# req: REQ-01, REQ-03, REQ-32, REQ-04, REQ-33, REQ-05, REQ-34, REQ-25, REQ-23
@cocotb.test()
async def test_reset_and_regs(dut):
    b = await setup(dut)
    m = Model()
    m.reset()
    assert await b.read(0x000) == ID == m.read_reg(0)
    assert await b.read(0x008) == 0
    for v in (0xDEADBEEF, 0xFFFFFFFF, 0x80000001, 0, 0x12345678):
        await b.write(0x008, v)
        assert await b.read(0x008) == v
        # hold until next h_re
        await b.cyc(12)
        assert int(dut.h_rdata.value) == v
    await b.write(0x008, 0xCAFEF00D)
    # writes to ID are ignored
    await b.write(0x000, 0x1234)
    assert await b.read(0x000) == ID
    # unmapped addresses read 0 and ignore writes
    for a in (0x034, 0x038, 0x03C, 0x040, 0x0FC, 0x100, 0x400, 0x7FC, 0xFFC, 0x00C, 0x01):
        await b.write(a, 0xFFFFFFFF)
    for a in (0x00C, 0x034, 0x040, 0x0FC, 0x100, 0x800, 0xFFC):
        assert await b.read(a) == 0, hex(a)
    assert await b.read(0x008) == 0xCAFEF00D
    assert await b.read(CTRL) == 0
    for a in (WW, WR, ERR, OVF, UNF, STALL, OCC):
        assert await b.read(a) == 0
    assert await b.read(SNAP) == 0
    # CTRL: RUN and SLOW stick, reserved read 0, CLEAR/INJECT read 0
    await b.write(CTRL, 0xFFFFFFF3)
    assert await b.read(CTRL) == 0x3
    await b.write(CTRL, SLOW)
    assert await b.read(CTRL) == SLOW
    await b.write(CTRL, CLEAR | SLOW)
    assert await b.read(CTRL) == SLOW
    await b.write(CTRL, 0)
    assert await b.read(CTRL) == 0
    # counters stay 0 with RUN=0
    assert await b.snapshot() == [0] * 7


# req: REQ-06, REQ-07, REQ-09, REQ-10, REQ-12, REQ-13, REQ-14, REQ-16
@cocotb.test()
async def test_run_clean(dut):
    b = await setup(dut)
    N = 3000
    await b.write(CTRL, CLEAR)
    await b.write(CTRL, RUN)
    await b.cyc(N)
    # live snapshot: reader never gets ahead of the writer, error free
    live = await b.snapshot()
    assert live[2] == 0 and live[3] == 0 and live[4] == 0
    assert live[1] <= live[0]
    assert live[0] - live[1] <= 512
    await b.drain()
    s = await b.snapshot()
    m = Model()
    m.reset()
    m.write_reg(CTRL, RUN)
    for _ in range(N + 8):
        m.step()
    m.write_reg(CTRL, 0)
    for _ in range(300):
        m.step()
    m.write_reg(SNAP, 1)
    exp = [m.read_reg(a) for a in (WW, WR, ERR, OVF, UNF, STALL, OCC)]
    assert abs(s[0] - exp[0]) <= 40, (s, exp)
    assert s[0] > N - 40
    assert s[1] == s[0], "all words read and checked"
    assert s[2] == 0 and s[3] == 0 and s[4] == 0 and s[5] == 0
    # fast reader keeps the FIFO nearly empty; a 512-deep FIFO never fills
    assert 1 <= s[6] <= 40, s
    assert (await b.read(CTRL)) == 0
    # restart without CLEAR stays aligned
    await b.write(CTRL, RUN)
    await b.cyc(500)
    await b.drain()
    s2 = await b.snapshot()
    assert s2[0] > s[0] + 400 and s2[1] == s2[0] and s2[2] == 0 and s2[3] == 0 and s2[4] == 0


# req: REQ-14, REQ-15, REQ-16, REQ-17, REQ-18, REQ-06, REQ-09
@cocotb.test()
async def test_slow_read(dut):
    b = await setup(dut)
    N = 6000
    await b.write(CTRL, CLEAR)
    await b.write(CTRL, RUN | SLOW)
    await b.cyc(N)
    s = await b.snapshot()
    # at most one pop per 8 gt cycles: N clk25 cycles = N*25/4 gt cycles
    maxpops = int(N * 25 / 4 / 8) + 40
    assert s[1] <= maxpops, (s, maxpops)
    assert s[1] > maxpops // 2
    assert s[5] > 0, "STALL_W non-zero when FIFO fills"
    assert 505 <= s[6] <= 512, s
    assert s[2] == 0 and s[3] == 0 and s[4] == 0
    m = Model()
    m.reset()
    m.write_reg(CTRL, RUN | SLOW)
    for _ in range(N + 8):
        m.step()
    m.write_reg(SNAP, 1)
    exp = m.read_reg(STALL)
    assert abs(s[5] - exp) <= max(100, exp // 10), (s, exp)
    # writer pushed words only while not full: written - read <= depth
    assert s[0] - s[1] <= 512 + 4
    s_a = s
    await b.cyc(1000)
    s_b = await b.snapshot()
    # each clk25 with FIFO full is a stall: stall grows ~ with time while full
    assert s_b[5] - s_a[5] > 500, (s_a, s_b)
    await b.drain()
    s_c = await b.snapshot()
    assert s_c[1] == s_c[0] and s_c[2] == 0 and s_c[3] == 0 and s_c[4] == 0


# req: REQ-19, REQ-20, REQ-10, REQ-25
@cocotb.test()
async def test_inject(dut):
    b = await setup(dut)
    await b.write(CTRL, CLEAR)
    await b.write(CTRL, RUN)
    await b.cyc(200)
    await b.write(CTRL, RUN | INJECT)
    assert await b.read(CTRL) == RUN
    await b.cyc(300)
    s = await b.snapshot()
    assert s[2] == 1, s
    await b.cyc(1000)
    s = await b.snapshot()
    assert s[2] == 1, "INJECT is self-clearing: exactly one word flipped"
    assert (int(dut.led.value) >> 1) & 1 == 1
    for k in range(2, 5):
        await b.write(CTRL, RUN | INJECT)
        await b.cyc(200)
        s = await b.snapshot()
        assert s[2] == k, (k, s)
    await b.drain()
    s = await b.snapshot()
    assert s[2] == 4 and s[1] == s[0]
    # INJECT ignored while RUN=0
    await b.write(CTRL, INJECT)
    await b.write(CTRL, RUN)
    await b.cyc(600)
    await b.drain()
    s = await b.snapshot()
    assert s[2] == 4, s


# req: REQ-24, REQ-36, REQ-37, REQ-08, REQ-25
@cocotb.test()
async def test_clear(dut):
    b = await setup(dut)
    await b.write(CTRL, RUN | SLOW)
    await b.cyc(3500)
    await b.write(CTRL, RUN | SLOW | INJECT)
    await b.cyc(100)
    s = await b.snapshot()
    assert s[0] > 0 and s[1] > 0 and s[2] == 1 and s[5] > 0 and s[6] > 0
    # CLEAR while RUN=1 changes no counter
    await b.write(CTRL, RUN | SLOW | CLEAR)
    s1 = await b.snapshot()
    assert s1[0] >= s[0] and s1[1] >= s[1] and s1[2] >= 1 and s1[5] >= s[5] and s1[6] >= s[6], (s, s1)
    assert await b.read(CTRL) == (RUN | SLOW)
    # stop; the FIFO still holds words (slow reader), then CLEAR while RUN=0
    await b.write(CTRL, SLOW)
    await b.write(CTRL, SLOW | CLEAR)
    assert await b.read(CTRL) == SLOW
    s2 = await b.snapshot()
    assert s2 == [0] * 7, s2
    assert (int(dut.led.value) >> 1) & 1 == 0, "error LED cleared by CLEAR"
    # both PRBS sequences restart: a fresh run is error free (needs FIFO emptied)
    await b.write(CTRL, RUN)
    await b.cyc(800)
    await b.drain()
    s3 = await b.snapshot()
    assert s3[0] > 700 and s3[1] == s3[0] and s3[2] == 0 and s3[3] == 0 and s3[4] == 0 and s3[5] == 0, s3
    # clear again after a run restarts words from 0
    await b.write(CTRL, CLEAR)
    assert await b.snapshot() == [0] * 7
    await b.write(CTRL, RUN)
    await b.cyc(300)
    await b.drain()
    s4 = await b.snapshot()
    assert s4[0] > 250 and s4[0] < s3[0] and s4[1] == s4[0] and s4[2] == 0


# req: REQ-21, REQ-22, REQ-23, REQ-35, REQ-25
@cocotb.test()
async def test_snapshot(dut):
    b = await setup(dut)
    await b.write(CTRL, CLEAR)
    assert await b.snapshot() == [0] * 7
    await b.write(CTRL, RUN | SLOW)
    await b.cyc(1500)
    # nothing visible before a SNAPSHOT write
    assert [await b.read(a) for a in (WW, WR, ERR, OVF, UNF, STALL, OCC)] == [0] * 7
    s = await b.snapshot()
    assert s[0] > 1000 and s[1] > 0 and s[0] >= s[1]
    assert s[0] - s[1] <= 512 + 4
    assert s[6] <= 0x3FF
    # values held while counters keep running
    await b.cyc(500)
    again = [await b.read(a) for a in (WW, WR, ERR, OVF, UNF, STALL, OCC)]
    assert again == s
    for a in (WW, WR, ERR, OVF, UNF, STALL, OCC):
        await b.write(a, 0xFFFFFFFF)  # read-only: ignored
    assert [await b.read(a) for a in (WW, WR, ERR, OVF, UNF, STALL, OCC)] == s
    s2 = await b.snapshot()
    assert s2[0] > s[0] + 400 and s2[1] > s[1]
    assert s2[0] < 0xFFFFFFFF  # 32-bit registers, no truncation to a few bits
    assert s2[5] >= s[5]
    await b.drain()


# req: REQ-26, REQ-10
@cocotb.test()
async def test_led_pins(dut):
    b = await setup(dut)
    names = b.names
    assert int(dut.led.value) == 0
    if "sfp_tx_disable" in names:
        assert int(dut.sfp_tx_disable.value) == 1
    await b.write(CTRL, RUN)
    await b.cyc(50)
    assert int(dut.led.value) == 1
    await b.write(CTRL, RUN | INJECT)
    await b.cyc(200)
    assert int(dut.led.value) == 3
    await b.write(CTRL, 0)
    await b.cyc(400)
    assert int(dut.led.value) == 2, "error flag sticky"
    await b.write(CTRL, CLEAR)
    await b.cyc(10)
    assert int(dut.led.value) == 0
    if "sfp_tx_disable" in names:
        assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-01, REQ-03, REQ-32, REQ-04, REQ-33, REQ-06, REQ-09, REQ-10, REQ-12, REQ-13, REQ-15, REQ-17, REQ-19, REQ-20, REQ-21, REQ-22, REQ-24, REQ-36, REQ-37, REQ-25
@cocotb.test()
async def test_random_traffic(dut):
    b = await setup(dut)
    seed = int(os.environ.get("RANDOM_SEED", os.environ.get("COCOTB_RANDOM_SEED", "1")))
    rnd = random.Random(seed)
    scratch = 0
    injects = 0
    total_w_prev = 0
    for phase in range(10):
        slow = rnd.choice([0, 0, 1])
        cycles = rnd.choice([150, 400, 900, 2800])
        if rnd.random() < 0.4:
            await b.write(CTRL, CLEAR)
            injects = 0
            total_w_prev = 0
            assert await b.snapshot() == [0] * 7
        await b.write(CTRL, RUN | (SLOW if slow else 0))
        done = 0
        while done < cycles:
            step = rnd.choice([40, 100, 150])
            await b.cyc(step)
            done += step
            op = rnd.choice(["inj", "scr", "unm", "snap", "rd", "clr1", "none"])
            if op == "inj" and done + 400 < cycles + 400:
                await b.write(CTRL, RUN | (SLOW if slow else 0) | INJECT)
                injects += 1
                await b.cyc(100 if not slow else 500)
                done += 100
            elif op == "scr":
                scratch = rnd.getrandbits(32)
                await b.write(0x008, scratch)
                assert await b.read(0x008) == scratch
            elif op == "unm":
                a = rnd.choice([0x00C, 0x034, 0x080, 0x3FC, 0xFF0])
                await b.write(a, rnd.getrandbits(32))
                assert await b.read(a) == 0
            elif op == "snap":
                s = await b.snapshot()
                assert s[3] == 0 and s[4] == 0
                assert s[1] <= s[0] + 0
                assert [await b.read(a) for a in (WW, WR, ERR, OVF, UNF, STALL, OCC)] == s
            elif op == "rd":
                assert await b.read(0x000) == ID
            elif op == "clr1":
                before = await b.snapshot()
                await b.write(CTRL, RUN | (SLOW if slow else 0) | CLEAR)
                after = await b.snapshot()
                assert after[0] >= before[0] and after[1] >= before[1] and after[2] >= before[2]
        await b.drain()
        s = await b.snapshot()
        assert s[0] == s[1], (phase, s)
        assert s[3] == 0 and s[4] == 0
        assert s[2] == injects, (phase, s, injects)
        assert s[0] >= total_w_prev
        total_w_prev = s[0]
        assert await b.read(0x008) == scratch
        assert await b.read(0x000) == ID
        assert await b.read(CTRL) == 0
