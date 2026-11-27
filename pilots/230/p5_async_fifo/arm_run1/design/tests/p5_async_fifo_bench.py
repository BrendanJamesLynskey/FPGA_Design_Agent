"""cocotb bench for the p5 async FIFO soak register core, checked against model.py.

The reader domain (clk_rd) is asynchronous to the register/writer domain (clk_wr), so
the bench compares with the model with tolerances where CDC latency matters and exactly
where state is quiescent (after a drain).
"""
import os
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402
from model import Model  # noqa: E402

W = int(os.environ.get("P5_COUNTER_WIDTH", "32"))
MASK = (1 << W) - 1

A_ID, A_BUILD, A_SCR, A_CTRL = 0x00, 0x04, 0x08, 0x10
A_WW, A_WR, A_ERR, A_OVF, A_UNF, A_STALL, A_OCC, A_SNAP = 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x2C, 0x30
CNT_ADDRS = [A_WW, A_WR, A_ERR, A_OVF, A_UNF, A_STALL, A_OCC]
UNMAPPED = [0x00C, 0x034, 0x038, 0x03C, 0x040, 0x100, 0x400, 0x800, 0xFFC]


def H(dut, *names):
    for n in names:
        if hasattr(dut, n):
            return getattr(dut, n)
    return None


def sdiff(a, b, mask=MASK):
    d = (a - b) & mask
    return d - (mask + 1) if d > (mask >> 1) else d


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.clkw = H(dut, "clk_wr", "clk")
        self.clkr = H(dut, "clk_rd")
        self.rst = H(dut, "rst")
        self.led = H(dut, "led")
        self.sfp = H(dut, "sfp_tx_disable")
        self.m = Model(COUNTER_WIDTH_BITS=W)
        self.cyc = 0

    async def start_clocks(self):
        for sig, per in ((self.clkw, 40000), (self.clkr, 6400)):
            if sig is None:
                continue
            try:
                clk = Clock(sig, per, units="ps")
            except TypeError:
                clk = Clock(sig, per, unit="ps")
            cocotb.start_soon(clk.start())

    async def monitor(self):
        while True:
            await RisingEdge(self.clkw)
            if self.sfp is not None and self.sfp.value.is_resolvable:
                assert int(self.sfp.value) == 1, "sfp_tx_disable dropped"

    def idle_inputs(self):
        self.dut.h_we.value = 0
        self.dut.h_re.value = 0
        self.dut.h_addr.value = 0
        self.dut.h_wdata.value = 0

    async def tick(self, n=1):
        for _ in range(n):
            await RisingEdge(self.clkw)
            self.cyc += 1
            self.m.step()

    async def wr(self, addr, val):
        self.dut.h_addr.value = addr
        self.dut.h_wdata.value = val
        self.dut.h_we.value = 1
        await RisingEdge(self.clkw)
        self.cyc += 1
        self.m.step({"h_we": 1, "h_addr": addr, "h_wdata": val})
        self.dut.h_we.value = 0
        await RisingEdge(self.clkw)
        self.cyc += 1
        self.m.step()

    async def rd(self, addr):
        self.dut.h_addr.value = addr
        self.dut.h_re.value = 1
        await RisingEdge(self.clkw)
        self.cyc += 1
        self.m.step({"h_re": 1, "h_addr": addr})
        self.dut.h_re.value = 0
        await RisingEdge(self.clkw)
        self.cyc += 1
        self.m.step()
        await RisingEdge(self.clkw)
        self.cyc += 1
        self.m.step()
        await Timer(1, "ns")
        return int(self.dut.h_rdata.value)

    async def snapshot(self):
        await self.wr(A_SNAP, 0)
        t = self.cyc
        self.msnap = list(self.m.snap)
        await self.tick(16)
        vals = []
        for a in CNT_ADDRS:
            vals.append(await self.rd(a))
        return {"t": t, "ww": vals[0], "wr": vals[1], "err": vals[2], "ovf": vals[3],
                "unf": vals[4], "stall": vals[5], "occ": vals[6], "raw": vals, "m": self.msnap}

    async def setup(self, first=False):
        await self.start_clocks()
        self.idle_inputs()
        cocotb.start_soon(self.monitor())
        if self.rst is not None:
            self.rst.value = 1
            await self.tick(10)
            self.rst.value = 0
            await self.tick(20)
        else:
            await self.tick(10)
        if not first:
            await self.wr(A_CTRL, 0)
            await self.tick(200)
            await self.wr(A_CTRL, 4)
            await self.tick(30)
            await self.wr(A_CTRL, 0)
            await self.wr(A_SCR, 0)
            await self.tick(4)
        self.m = Model(COUNTER_WIDTH_BITS=W)

    def led_val(self):
        return int(self.led.value) if self.led is not None else None


def check_clean(s, why=""):
    assert s["ovf"] == 0, f"OVERFLOWS nonzero {why} {s}"
    assert s["unf"] == 0, f"UNDERFLOWS nonzero {why} {s}"


# req: REQ-01, REQ-02, REQ-03, REQ-04, REQ-24
@cocotb.test()
async def test_reset_and_id(dut):
    b = Bench(dut)
    await b.setup(first=True)
    assert await b.rd(A_ID) == 0x20950001
    assert await b.rd(A_ID) == b.m.read_reg(A_ID)
    await b.rd(A_BUILD)  # value is the bitstream stamp: only readable here
    assert await b.rd(A_SCR) == 0 == b.m.read_reg(A_SCR)
    assert await b.rd(A_CTRL) == 0
    for a in CNT_ADDRS + [A_SNAP]:
        assert await b.rd(a) == 0, f"reg {a:#x} not 0 at reset"
    for a in UNMAPPED:
        assert await b.rd(a) == 0, f"unmapped {a:#x} not 0"
    if b.sfp is not None:
        assert int(b.sfp.value) == 1
    if b.led is not None:
        assert b.led_val() == 0


# req: REQ-02, REQ-04, REQ-29, REQ-30
@cocotb.test()
async def test_scratch_and_unmapped_writes(dut):
    b = Bench(dut)
    await b.setup()
    assert await b.rd(A_SCR) == 0
    for v in (0xFFFFFFFF, 0xA5A5A5A5, 0x5A5A5A5A, 1, 0x80000000, 0):
        await b.wr(A_SCR, v)
        assert await b.rd(A_SCR) == v
        b.m.write_reg(A_SCR, v)
        assert b.m.read_reg(A_SCR) == v
    await b.wr(A_SCR, 0x12345678)
    idv = await b.rd(A_ID)
    build = await b.rd(A_BUILD)
    for a in UNMAPPED + [A_ID, A_BUILD] + CNT_ADDRS:
        await b.wr(a, 0xFFFFFFFF)
    assert await b.rd(A_SCR) == 0x12345678
    assert await b.rd(A_ID) == idv
    assert await b.rd(A_BUILD) == build
    assert await b.rd(A_CTRL) == 0
    for a in CNT_ADDRS + [A_SNAP]:
        assert await b.rd(a) == 0
    for a in UNMAPPED:
        assert await b.rd(a) == 0
    # a snapshot after the junk writes still reads zeros (nothing started)
    s = await b.snapshot()
    assert s["raw"] == [0] * 7


# req: REQ-05, REQ-31
@cocotb.test()
async def test_read_latency_and_hold(dut):
    b = Bench(dut)
    await b.setup()
    await b.wr(A_SCR, 0xCAFEBABE)
    for addr, exp in ((A_ID, 0x20950001), (A_SCR, 0xCAFEBABE), (0x100, 0), (A_ID, 0x20950001)):
        dut.h_addr.value = addr
        dut.h_re.value = 1
        await RisingEdge(b.clkw)
        dut.h_re.value = 0
        await RisingEdge(b.clkw)
        await RisingEdge(b.clkw)
        await Timer(1, "ns")
        assert int(dut.h_rdata.value) == exp, f"h_rdata {int(dut.h_rdata.value):#x} != {exp:#x} at 2 clocks"
        for i in range(12):
            # address changes without h_re: value must hold
            dut.h_addr.value = (A_SCR, A_ID, 0x30, A_CTRL)[i % 4]
            await RisingEdge(b.clkw)
            await Timer(1, "ns")
            assert int(dut.h_rdata.value) == exp, "h_rdata did not hold"
    dut.h_addr.value = 0
    # a new read replaces the held value
    assert await b.rd(A_SCR) == 0xCAFEBABE


# req: REQ-06, REQ-08, REQ-10, REQ-11, REQ-12, REQ-23, REQ-24
@cocotb.test()
async def test_run_fast(dut):
    b = Bench(dut)
    await b.setup()
    await b.wr(A_CTRL, 1)
    await b.tick(40)
    if b.led is not None:
        assert b.led_val() & 1 == 1
    await b.tick(1500)
    s1 = await b.snapshot()
    check_clean(s1, "mid-run")
    assert s1["err"] == 0
    assert s1["stall"] == 0
    assert abs(sdiff(s1["ww"], s1["m"][0])) <= 8, (s1["ww"], s1["m"][0])
    await b.tick(60)
    s2 = await b.snapshot()
    dt = s2["t"] - s1["t"]
    assert abs(sdiff(s2["ww"], s1["ww"]) - dt) <= 4, "writer must write every clock"
    assert 1 <= s2["occ"] <= 64
    await b.wr(A_CTRL, 0)
    await b.tick(200)
    s3 = await b.snapshot()
    check_clean(s3, "after drain")
    assert s3["err"] == 0 and s3["stall"] == 0
    assert s3["ww"] == s3["wr"], "reader must drain and check every word written"
    assert abs(sdiff(s3["ww"], s3["m"][0])) <= 8
    await b.tick(100)
    s4 = await b.snapshot()
    assert s4["ww"] == s3["ww"] and s4["wr"] == s3["wr"], "writer must stop with RUN 0"
    if b.led is not None:
        assert b.led_val() == 0
        assert b.led_val() == b.m.step()["led"]


# req: REQ-09, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-22, REQ-06
@cocotb.test()
async def test_slow_read_fill(dut):
    b = Bench(dut)
    await b.setup()
    await b.wr(A_CTRL, 3)
    await b.tick(3500)
    s1 = await b.snapshot()
    assert s1["occ"] == 512, f"FIFO must fill to 512 words, OCC_MAX={s1['occ']}"
    check_clean(s1, "slow fill")
    assert s1["err"] == 0
    await b.tick(60)
    s2 = await b.snapshot()
    dt = s2["t"] - s1["t"]
    dr = sdiff(s2["wr"], s1["wr"])
    dw = sdiff(s2["ww"], s1["ww"])
    ds = sdiff(s2["stall"], s1["stall"])
    exp_r = dt * 6.25 / 8
    assert dr <= exp_r + 4, f"reader too fast with SLOW_READ: {dr} words in {dt} wr clocks"
    assert dr >= exp_r - 4, f"reader too slow: {dr} vs {exp_r}"
    assert ds >= 8, "STALL_W must increment while full"
    assert abs(ds + dw - dt) <= 4, "every run clock is a write or a stall"
    assert s2["occ"] == 512
    assert abs(sdiff(s2["ww"], s2["m"][0])) <= 16
    await b.wr(A_CTRL, 0)
    await b.tick(250)
    s3 = await b.snapshot()
    check_clean(s3, "slow drain")
    assert s3["err"] == 0
    assert s3["ww"] == s3["wr"]
    assert s3["occ"] == 512


# req: REQ-07, REQ-08, REQ-15, REQ-16, REQ-33, REQ-12
@cocotb.test()
async def test_inject(dut):
    b = Bench(dut)
    await b.setup()
    await b.wr(A_CTRL, 1)
    await b.tick(100)
    s = await b.snapshot()
    assert s["err"] == 0
    await b.wr(A_CTRL, 9)
    await b.tick(100)
    s = await b.snapshot()
    assert s["err"] == 1, f"INJECT must give exactly one error, got {s['err']}"
    assert (await b.rd(A_CTRL)) & 8 == 0, "INJECT must self-clear"
    await b.tick(1500)
    s = await b.snapshot()
    assert s["err"] == 1, "INJECT must not corrupt more than one word"
    await b.wr(A_CTRL, 9)
    await b.tick(100)
    s = await b.snapshot()
    assert s["err"] == 2
    await b.wr(A_CTRL, 0)
    await b.tick(200)
    s = await b.snapshot()
    check_clean(s)
    assert s["err"] == 2 and s["ww"] == s["wr"]
    assert s["err"] == s["m"][2]
    if b.led is not None:
        assert b.led_val() == 2, "led[1] flags errors, led[0] is RUN"
    # inject with a deep FIFO (slow read): still exactly one more error
    await b.wr(A_CTRL, 3)
    await b.tick(3000)
    await b.wr(A_CTRL, 0xB)
    await b.tick(100)
    s = await b.snapshot()
    assert s["err"] == 3
    await b.wr(A_CTRL, 0)
    await b.tick(250)
    s = await b.snapshot()
    check_clean(s)
    assert s["err"] == 3 and s["ww"] == s["wr"]


# req: REQ-17, REQ-18, REQ-19, REQ-34, REQ-22, REQ-10, REQ-11, REQ-12
@cocotb.test()
async def test_clear(dut):
    b = Bench(dut)
    await b.setup()
    # (a) clear with RUN 0 and a non-empty FIFO and nonzero counters
    await b.wr(A_CTRL, 3)
    await b.tick(3000)
    await b.wr(A_CTRL, 2)
    await b.tick(5)
    s = await b.snapshot()
    assert s["occ"] == 512
    await b.wr(A_CTRL, 6)
    await b.tick(10)
    assert (await b.rd(A_CTRL)) & 4 == 0, "CLEAR must self-clear"
    assert (await b.rd(A_CTRL)) & 3 == 2
    s = await b.snapshot()
    assert s["raw"] == [0] * 7, f"CLEAR must zero every counter and OCC_MAX: {s['raw']}"
    await b.tick(300)
    s = await b.snapshot()
    assert s["raw"] == [0] * 7, f"FIFO must be empty after CLEAR: {s['raw']}"
    # (b) sequences restart from the seed: no data errors after a fresh run
    await b.wr(A_CTRL, 1)
    await b.tick(500)
    await b.wr(A_CTRL, 0)
    await b.tick(200)
    s = await b.snapshot()
    assert s["err"] == 0, "both PRBS copies must restart from the seed after CLEAR"
    check_clean(s)
    assert s["ww"] == s["wr"]
    assert abs(sdiff(s["ww"], s["m"][0])) <= 8
    assert s["occ"] >= 1
    # (c) clear while RUN 1 is ignored
    await b.wr(A_CTRL, 1)
    await b.tick(100)
    sa = await b.snapshot()
    await b.wr(A_CTRL, 5)
    await b.tick(40)
    sb = await b.snapshot()
    assert (await b.rd(A_CTRL)) & 4 == 0, "ignored CLEAR must still self-clear"
    el = sb["t"] - sa["t"]
    assert abs(sdiff(sb["ww"], sa["ww"]) - el) <= 4, "CLEAR with RUN 1 must not zero counters"
    assert sb["occ"] >= sa["occ"] and sb["occ"] >= 1
    await b.wr(A_CTRL, 0)
    await b.tick(200)
    s = await b.snapshot()
    assert s["err"] == 0
    check_clean(s)
    assert s["ww"] == s["wr"]
    assert abs(sdiff(s["ww"], s["m"][0])) <= 12
    # no latent clear after the run stopped
    await b.tick(50)
    s2 = await b.snapshot()
    assert s2["ww"] == s["ww"] and s2["wr"] == s["wr"]
    # (d) a second clear, then re-run: sequences again aligned
    await b.wr(A_CTRL, 4)
    await b.tick(10)
    s = await b.snapshot()
    assert s["raw"] == [0] * 7
    await b.wr(A_CTRL, 1)
    await b.tick(333)
    await b.wr(A_CTRL, 0)
    await b.tick(200)
    s = await b.snapshot()
    assert s["err"] == 0 and s["ww"] == s["wr"]


# req: REQ-20, REQ-06, REQ-14
@cocotb.test()
async def test_snapshot_atomic(dut):
    b = Bench(dut)
    await b.setup()
    await b.wr(A_CTRL, 3)
    t_run = b.cyc
    await b.tick(2600)
    A = await b.snapshot()
    el = A["t"] - t_run
    assert abs(sdiff(A["ww"] + A["stall"], el)) <= 8, "snapshot must be taken at one instant"
    if W >= 16:
        d = sdiff(A["ww"], A["wr"])
        assert -8 <= d <= 520, f"WORDS_W - WORDS_R inconsistent: {d}"
    # latched values hold while counters run
    await b.tick(300)
    B = [await b.rd(a) for a in CNT_ADDRS]
    assert B == A["raw"], "snapshot registers must hold until the next SNAPSHOT"
    C = await b.snapshot()
    assert C["raw"] != A["raw"]
    el = C["t"] - t_run
    assert abs(sdiff(C["ww"] + C["stall"], el)) <= 8
    assert abs(sdiff(C["ww"], C["m"][0])) <= 16
    await b.wr(A_CTRL, 0)
    await b.tick(250)


# req: REQ-21, REQ-32, REQ-22
@cocotb.test()
async def test_counter_wrap(dut):
    b = Bench(dut)
    await b.setup()
    await b.wr(A_CTRL, 1)
    await b.tick(1000)
    await b.wr(A_CTRL, 0)
    await b.tick(200)
    s = await b.snapshot()
    assert s["ww"] == s["wr"]
    assert s["ww"] <= MASK
    assert abs(sdiff(s["ww"], s["m"][0])) <= 6, (
        f"counter width {W}: RTL {s['ww']} vs model {s['m'][0]} (wrap)")
    assert abs(sdiff(s["wr"], s["m"][1])) <= 6
    if W >= 16:
        assert s["ww"] > 255, "counters must be wider than 8 bits"
    else:
        assert s["ww"] < 256
    # stall counter wraps the same way (slow fill)
    await b.wr(A_CTRL, 3)
    await b.tick(4000)
    s = await b.snapshot()
    assert abs(sdiff(s["stall"], s["m"][5], MASK)) <= 40
    assert s["occ"] == 512, "OCC_MAX is 10 bits and does not wrap with the counters"
    await b.wr(A_CTRL, 0)
    await b.tick(250)


# req: REQ-24, REQ-10, REQ-11
@cocotb.test()
async def test_sfp_pins_and_led(dut):
    b = Bench(dut)
    await b.setup()
    for v in (0, 1, 3, 2, 1, 0):
        await b.wr(A_CTRL, v)
        await b.tick(60)
        if b.sfp is not None:
            assert int(b.sfp.value) == 1
        if b.led is not None and v in (0, 1):
            assert b.led_val() & 1 == v & 1
    await b.tick(250)
    s = await b.snapshot()
    check_clean(s)
    assert s["err"] == 0
    if b.sfp is not None:
        assert int(b.sfp.value) == 1


# req: REQ-01, REQ-02, REQ-04, REQ-06, REQ-08, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14, REQ-15, REQ-17, REQ-18, REQ-20, REQ-29, REQ-30, REQ-34
@cocotb.test()
async def test_random_traffic(dut):
    b = Bench(dut)
    await b.setup()
    rng = random.Random(cocotb.RANDOM_SEED)
    run, slow = 0, 0
    exp_err = 0
    scratch = 0
    for seg in range(14):
        act = rng.choice(["run", "run", "stop", "scratch", "clear", "inject", "unmapped"])
        if act == "run":
            run, slow = 1, rng.randint(0, 1)
            await b.wr(A_CTRL, 1 | (slow << 1))
            await b.tick(rng.randint(50, 1200))
        elif act == "stop":
            run = 0
            slow = rng.randint(0, 1)
            await b.wr(A_CTRL, slow << 1)
            await b.tick(rng.randint(20, 300))
        elif act == "scratch":
            scratch = rng.choice([0, 1, 0xFFFFFFFF, rng.getrandbits(32)])
            await b.wr(A_SCR, scratch)
            assert await b.rd(A_SCR) == scratch
        elif act == "unmapped":
            await b.wr(rng.choice(UNMAPPED), rng.getrandbits(32))
            assert await b.rd(A_SCR) == scratch
            assert await b.rd(rng.choice(UNMAPPED)) == 0
        elif act == "inject" and run:
            await b.wr(A_CTRL, 9 | (slow << 1))
            exp_err = (exp_err + 1) & MASK
            await b.tick(100)
        elif act == "clear":
            if run:
                # ignored while running
                await b.wr(A_CTRL, 5 | (slow << 1))
                await b.tick(20)
            else:
                await b.wr(A_CTRL, 4 | (slow << 1))
                await b.tick(20)
                s = await b.snapshot()
                assert s["raw"] == [0] * 7, "CLEAR with RUN 0 must zero all"
                exp_err = 0
        s = await b.snapshot()
        check_clean(s, f"segment {seg} {act}")
        assert s["err"] == exp_err, f"segment {seg} {act}: errs {s['err']} expected {exp_err}"
        assert s["occ"] <= 512
        assert abs(sdiff(s["ww"], s["m"][0])) <= 24, (seg, act, s["ww"], s["m"][0])
        if W >= 16 and s["ww"] < 2**15 and s["wr"] < 2**15:
            assert -8 <= sdiff(s["ww"], s["wr"]) <= 520
        assert await b.rd(A_SCR) == scratch
    await b.wr(A_CTRL, 0)
    await b.tick(250)
    s = await b.snapshot()
    check_clean(s, "final")
    assert s["err"] == exp_err
    assert s["ww"] == s["wr"], "all written words must be read and checked"
