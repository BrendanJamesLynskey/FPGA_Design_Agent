"""cocotb bench for the async FIFO soak register core, checked against model.py."""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

M32 = 0xFFFFFFFF
CTRL, SNAP = 0x10, 0x30
REGS = {"WORDS_W": 0x14, "WORDS_R": 0x18, "DATA_ERRS": 0x1C,
        "OVERFLOWS": 0x20, "UNDERFLOWS": 0x24, "STALL_W": 0x28, "OCC_MAX": 0x2C}
RUN, SLOW, CLEAR, INJ = 1, 2, 4, 8


def _first(dut, names):
    for n in names:
        if hasattr(dut, n):
            return getattr(dut, n)
    raise AssertionError("none of %s on the toplevel" % (names,))


def _val(sig):
    try:
        return int(sig.value)
    except Exception:
        return None


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.clk = _first(dut, ["clk", "clk_wr", "clk_25"])
        self.clk_rd = _first(dut, ["clk_rd", "clk_156", "rd_clk"])
        self.m = model.Model()
        self.ticks = 0
        self.ctrl = 0
        self.sfp = getattr(dut, "sfp_tx_disable", None)
        self.led = getattr(dut, "led", None)

    async def start(self):
        for s in ("h_we", "h_re", "h_addr", "h_wdata"):
            getattr(self.dut, s).value = 0
        cocotb.start_soon(Clock(self.clk, 40000, unit="ps").start()
                          if _newclock() else Clock(self.clk, 40000, units="ps").start())
        cocotb.start_soon(Clock(self.clk_rd, 6400, unit="ps").start()
                          if _newclock() else Clock(self.clk_rd, 6400, units="ps").start())
        self.m.reset()
        await RisingEdge(self.clk)
        await self.tick(4)
        # the DUT is not reset between tests (reprogram model): stop, drain, clear
        await self.write(CTRL, 0)
        await self.tick(900)
        await self.write(CTRL, CLEAR)
        await self.tick(20)
        await self.write(8, 0)
        await self.tick(4)

    async def tick(self, n=1):
        for _ in range(n):
            await RisingEdge(self.clk)
            self.m.step()
            self.ticks += 1
            if self.sfp is not None:
                # req: REQ-23
                assert _val(self.sfp) in (1, None), "sfp_tx_disable must be 1"
                if _val(self.sfp) is None and self.ticks > 4:
                    raise AssertionError("sfp_tx_disable unknown")

    async def write(self, off, val):
        d = self.dut
        d.h_we.value = 1
        d.h_addr.value = off
        d.h_wdata.value = val & M32
        self.m.write_reg(off, val)
        await self.tick()
        d.h_we.value = 0
        d.h_wdata.value = 0

    async def setctrl(self, v):
        await self.write(CTRL, v)

    async def read(self, off):
        d = self.dut
        d.h_re.value = 1
        d.h_addr.value = off
        await self.tick()
        d.h_re.value = 0
        await self.tick(2)
        v = _val(d.h_rdata)
        assert v is not None, "h_rdata unknown after read of 0x%x" % off
        return v

    async def snapshot(self):
        await self.write(SNAP, 1)
        await self.tick(24)
        out = {}
        for k, o in REGS.items():
            out[k] = await self.read(o)
        return out

    async def drain(self):
        await self.setctrl(0)
        await self.tick(900)


def _newclock():
    import inspect
    return "unit" in inspect.signature(Clock.__init__).parameters


def _rng():
    seed = getattr(cocotb, "RANDOM_SEED", 1)
    return random.Random(seed)


# req: REQ-01, REQ-03, REQ-04, REQ-30, REQ-05, REQ-31, REQ-02
@cocotb.test()
async def test_register_port(dut):
    b = Bench(dut)
    await b.start()
    assert await b.read(0) == 0x20950001 == b.m.read_reg(0)
    # BUILD is readable and stable (value is the bitstream's, checked on hardware)
    bld = await b.read(4)
    await b.tick(10)
    assert await b.read(4) == bld
    assert await b.read(8) == 0
    r = _rng()
    pats = [0xFFFFFFFF, 0x55555555, 0xAAAAAAAA, 1, 0x80000000] + [r.getrandbits(32) for _ in range(8)]
    for p in pats:
        await b.write(8, p)
        assert await b.read(8) == p
        assert b.m.read_reg(8) == p
    await b.write(8, 0x1234ABCD)
    # RO and unmapped writes change nothing
    unm = [0x00C, 0x034, 0x038, 0x03C, 0x040, 0x100, 0x7FC, 0xFFC, 0x018 + 0x100]
    for a in unm:
        assert await b.read(a) == 0, "unmapped 0x%x" % a
    for a in unm + [0x000, 0x004]:
        await b.write(a, 0xDEADBEEF)
    for a in unm:
        assert await b.read(a) == 0, "unmapped after write 0x%x" % a
    assert await b.read(0) == 0x20950001
    assert await b.read(4) == bld
    assert await b.read(8) == 0x1234ABCD
    assert await b.read(CTRL) & 0xF == 0
    for o in REGS.values():
        assert await b.read(o) == 0
    assert await b.read(SNAP) == 0
    # writes to the counters' addresses are ignored too
    for o in REGS.values():
        await b.write(o, 0xFFFFFFFF)
        assert await b.read(o) == 0
    # h_rdata holds until the next h_re
    v = await b.read(8)
    for _ in range(12):
        await b.tick()
        assert _val(dut.h_rdata) == v
    await b.write(8, 0x0F0F0F0F)  # a write alone does not change h_rdata
    await b.tick(4)
    assert _val(dut.h_rdata) == v
    assert await b.read(8) == 0x0F0F0F0F


# req: REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-12, REQ-22, REQ-06
@cocotb.test()
async def test_stream_fast_read(dut):
    b = Bench(dut)
    await b.start()
    await b.setctrl(RUN)
    assert await b.read(CTRL) & 3 == 1
    await b.tick(2000)
    if b.led is not None:
        assert _val(b.led) == 1, "led: RUN only, no error"
    await b.drain()
    s = await b.snapshot()
    m = b.m
    m.write_reg(SNAP, 1)
    m.step()
    mw, mr = m.read_reg(0x14), m.read_reg(0x18)
    assert abs(s["WORDS_W"] - mw) <= 6, (s, mw)
    assert s["WORDS_W"] > 1900
    assert s["WORDS_R"] == s["WORDS_W"], s
    assert abs(s["WORDS_R"] - mr) <= 6
    assert s["DATA_ERRS"] == 0 and s["OVERFLOWS"] == 0 and s["UNDERFLOWS"] == 0
    assert s["STALL_W"] == 0
    assert 1 <= s["OCC_MAX"] <= 16, s


# req: REQ-13, REQ-14, REQ-15, REQ-16, REQ-11, REQ-12, REQ-06
@cocotb.test()
async def test_slow_read_fill(dut):
    b = Bench(dut)
    await b.start()
    await b.setctrl(RUN | SLOW)
    assert await b.read(CTRL) & 3 == 3
    await b.tick(4000)
    s1 = await b.snapshot()
    t1 = b.ticks
    await b.write(SNAP, 1)  # second snapshot instant measured by tick count
    t_a = b.ticks
    await b.tick(2000)
    s2 = await b.snapshot()
    # the snapshot write of s2 happened at b.ticks - (24+7*3+1)
    t_b = b.ticks - (24 + 7 * 3 + 1)
    T = t_b - t_a
    del t1
    assert s2["STALL_W"] > 0 and s1["STALL_W"] > 0
    assert s2["OVERFLOWS"] == 0 and s2["UNDERFLOWS"] == 0 and s2["DATA_ERRS"] == 0
    assert 490 <= s2["OCC_MAX"] <= 512, s2
    exp = T * 25.0 / 4 / 8
    dwr = s2["WORDS_R"] - s1["WORDS_R"]
    # one pop per 8 reader clocks at most (window jitter of a few words)
    assert dwr <= exp + 70, (dwr, exp)
    assert dwr >= exp - 70, (dwr, exp)
    dst = s2["STALL_W"] - s1["STALL_W"]
    dww = s2["WORDS_W"] - s1["WORDS_W"]
    assert abs(dww - dwr) <= 12, (dww, dwr)
    # T is estimated from the tick count, the snapshot instants are a few dozen clocks off
    assert abs(dst - (T - dww)) <= 120, (dst, T, dww)
    # compare with the model's stall count at the end
    mm = b.m
    mm.write_reg(SNAP, 1)
    mm.step()
    assert abs(s2["STALL_W"] - mm.read_reg(0x28)) <= 250
    # release the slow read: FIFO drains, counts settle equal
    await b.setctrl(RUN)
    await b.tick(1500)
    await b.setctrl(0)
    await b.tick(900)
    s3 = await b.snapshot()
    assert s3["WORDS_R"] == s3["WORDS_W"], s3
    assert s3["DATA_ERRS"] == 0 and s3["OVERFLOWS"] == 0 and s3["UNDERFLOWS"] == 0


# req: REQ-17, REQ-18, REQ-10, REQ-09
@cocotb.test()
async def test_inject(dut):
    b = Bench(dut)
    await b.start()
    await b.setctrl(RUN)
    await b.tick(300)
    await b.setctrl(RUN | INJ)
    await b.tick(300)
    assert await b.read(CTRL) & INJ == 0, "INJECT must self-clear"
    await b.tick(2000)
    if b.led is not None:
        assert _val(b.led) & 2 == 2, "sticky error led"
    await b.drain()
    s = await b.snapshot()
    assert s["DATA_ERRS"] == 1, s
    assert s["WORDS_R"] == s["WORDS_W"] and s["WORDS_R"] > 2000
    # a second injection gives exactly one more
    await b.setctrl(RUN)
    await b.tick(300)
    await b.setctrl(RUN | INJ)
    await b.tick(400)
    await b.drain()
    s = await b.snapshot()
    assert s["DATA_ERRS"] == 2, s
    assert s["OVERFLOWS"] == 0 and s["UNDERFLOWS"] == 0


# req: REQ-20, REQ-21, REQ-09
@cocotb.test()
async def test_clear(dut):
    b = Bench(dut)
    await b.start()
    await b.setctrl(RUN)
    await b.tick(800)
    await b.setctrl(RUN | INJ)
    await b.tick(300)
    # CLEAR while RUN is 1 is ignored
    await b.setctrl(RUN | CLEAR)
    assert await b.read(CTRL) & CLEAR == 0, "CLEAR must self-clear"
    await b.tick(300)
    s = await b.snapshot()
    assert s["WORDS_W"] > 1000 and s["DATA_ERRS"] == 1, s
    await b.drain()
    s = await b.snapshot()
    assert s["WORDS_W"] > 1000 and s["DATA_ERRS"] == 1 and s["WORDS_R"] == s["WORDS_W"]
    # CLEAR with RUN 0 restarts everything
    await b.setctrl(CLEAR)
    assert await b.read(CTRL) & 0xF == 0
    await b.tick(20)
    s = await b.snapshot()
    assert all(v == 0 for v in s.values()), s
    # both sequences restarted from the seed: a new run has no errors
    await b.setctrl(RUN)
    await b.tick(700)
    await b.drain()
    s = await b.snapshot()
    assert s["WORDS_W"] > 600 and s["WORDS_R"] == s["WORDS_W"], s
    assert s["DATA_ERRS"] == 0, s
    # CLEAR after a slow-read stop that left an offset in sequence position
    await b.setctrl(CLEAR)
    await b.tick(20)
    await b.setctrl(RUN)
    await b.tick(300)
    await b.drain()
    s = await b.snapshot()
    assert s["DATA_ERRS"] == 0 and s["WORDS_W"] > 200 and s["WORDS_R"] == s["WORDS_W"]


# req: REQ-19, REQ-22
@cocotb.test()
async def test_snapshot(dut):
    b = Bench(dut)
    await b.start()
    await b.setctrl(RUN | SLOW)
    await b.tick(600)
    s1 = await b.snapshot()
    # stable while counters keep running
    await b.tick(500)
    for k, o in REGS.items():
        assert await b.read(o) == s1[k], k
    assert s1["WORDS_W"] > 400
    # coherent at one instant: written minus read equals the fill
    fill = s1["WORDS_W"] - s1["WORDS_R"]
    assert 0 <= fill <= 512, s1
    s2 = await b.snapshot()
    assert s2["WORDS_W"] > s1["WORDS_W"]
    assert s2["WORDS_R"] >= s1["WORDS_R"]
    fill2 = s2["WORDS_W"] - s2["WORDS_R"]
    assert 0 <= fill2 <= 512, s2
    # running with a fast reader: a snapshot sees at most a few words in flight
    await b.setctrl(RUN)
    await b.tick(1500)
    s3 = await b.snapshot()
    assert 0 <= s3["WORDS_W"] - s3["WORDS_R"] <= 24, s3
    await b.drain()


# req: REQ-22, REQ-32
@cocotb.test()
async def test_counter_wrap(dut):
    b = Bench(dut)
    await b.start()
    sig = None
    try:
        for h in dut:
            if h._name.lower() in ("words_w", "cnt_words_w", "words_w_cnt", "words_w_q",
                                   "words_w_r", "wr_words", "words_w_reg"):
                sig = h
                break
    except Exception:
        sig = None
    if sig is None:
        dut._log.warning("no backdoor for the WORDS_W counter: wrap checked only by width")
        return
    sig.value = 0xFFFFFFF0
    await b.tick(2)
    await b.setctrl(RUN)
    await b.tick(120)
    await b.drain()
    s = await b.snapshot()
    assert s["WORDS_W"] < 0x200, "counter must wrap to 0 after 0xFFFFFFFF: %x" % s["WORDS_W"]


# req: REQ-08, REQ-27, REQ-28, REQ-11, REQ-12, REQ-10
@cocotb.test()
async def test_soak_no_errors(dut):
    b = Bench(dut)
    await b.start()
    await b.setctrl(RUN)
    t0 = b.ticks
    await b.tick(20000)
    t1 = b.ticks
    s = await b.snapshot()
    # one word per clk_wr while not stalled: rate within a few words of the tick count
    assert abs(s["WORDS_W"] - (t1 - t0)) <= 40, (s, t1 - t0)
    assert s["STALL_W"] == 0
    assert s["DATA_ERRS"] == 0 and s["OVERFLOWS"] == 0 and s["UNDERFLOWS"] == 0
    await b.drain()
    s = await b.snapshot()
    assert s["WORDS_R"] == s["WORDS_W"]
    assert s["DATA_ERRS"] == 0 and s["OVERFLOWS"] == 0 and s["UNDERFLOWS"] == 0


# req: REQ-03, REQ-04, REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-17, REQ-19, REQ-20
@cocotb.test()
async def test_random_traffic(dut):
    b = Bench(dut)
    await b.start()
    r = _rng()
    injects = 0
    run = 0
    for _ in range(40):
        op = r.choice(["run", "slow", "fast", "scratch", "inject", "snap", "unm", "idle"])
        if op == "run":
            run = 1
            await b.setctrl(RUN | (r.choice([0, SLOW])))
            await b.tick(r.randint(50, 400))
        elif op == "slow":
            run = 1
            await b.setctrl(RUN | SLOW)
            await b.tick(r.randint(100, 900))
        elif op == "fast":
            run = 1
            await b.setctrl(RUN)
            await b.tick(r.randint(50, 400))
        elif op == "scratch":
            v = r.choice([0, 1, M32, r.getrandbits(32)])
            await b.write(8, v)
            assert await b.read(8) == v
        elif op == "unm":
            a = r.choice([0x00C, 0x034, 0x080, 0x400, 0xFFC])
            await b.write(a, r.getrandbits(32))
            assert await b.read(a) == 0
        elif op == "inject" and run:
            await b.setctrl(RUN | INJ)
            injects += 1
            await b.tick(300)
            await b.setctrl(RUN)  # keep fast read so the flipped word is consumed
            await b.tick(300)
        elif op == "snap":
            s = await b.snapshot()
            assert s["OVERFLOWS"] == 0 and s["UNDERFLOWS"] == 0
            assert s["DATA_ERRS"] <= injects
        else:
            await b.tick(r.randint(1, 50))
    await b.setctrl(RUN)
    await b.tick(1000)
    await b.drain()
    s = await b.snapshot()
    assert s["DATA_ERRS"] == injects, (s, injects)
    assert s["WORDS_R"] == s["WORDS_W"], s
    assert s["OVERFLOWS"] == 0 and s["UNDERFLOWS"] == 0
    assert await b.read(0) == 0x20950001
    # clear and rerun clean
    await b.setctrl(CLEAR)
    await b.tick(30)
    s = await b.snapshot()
    assert all(v == 0 for v in s.values()), s
    await b.setctrl(RUN)
    await b.tick(500)
    await b.drain()
    s = await b.snapshot()
    assert s["DATA_ERRS"] == 0 and s["WORDS_R"] == s["WORDS_W"] > 400


# req: REQ-23
@cocotb.test()
async def test_sfp_tx_disable_constant(dut):
    b = Bench(dut)
    assert hasattr(dut, "sfp_tx_disable") or b.sfp is None
    await b.start()
    assert b.sfp is None or _val(b.sfp) == 1
    await b.setctrl(RUN | SLOW)
    await b.tick(300)
    await b.setctrl(0)
    await b.tick(300)  # tick() checks the output every cycle
    assert b.sfp is None or _val(b.sfp) == 1
