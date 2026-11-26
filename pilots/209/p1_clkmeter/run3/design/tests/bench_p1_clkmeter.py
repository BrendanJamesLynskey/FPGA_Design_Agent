"""cocotb bench for the p1 clock frequency meter register core, checked against model.py."""
import os
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

# small values for the long timing parameters (the pytest entry passes the same to the RTL)
LED_C3_HALF = 24
LED_REF_HALF = 125
PARAMS = dict(LED_C3_HALF_PERIOD_CYCLES=LED_C3_HALF, LED_REF_HALF_PERIOD_CYCLES=LED_REF_HALF)

ID, BUILD, SCRATCH, GATE_LEN, CTRL, STATUS, COUNT, ACTUAL, MEAS = 0, 4, 8, 16, 20, 24, 28, 32, 36
DEFAULT_GATE = 156250000
MASKS = [0, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555, 0x80000000, 1, 0x12345678, 0xDEADBEEF]


def pick(dut, *names):
    for n in names:
        if hasattr(dut, n):
            return getattr(dut, n)
    return None


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.c3 = pick(dut, "clk", "clk_c3", "clk_c3_in")
        self.ref = pick(dut, "clk_ref", "ref_clk")
        self.rst = pick(dut, "rst", "rst_c3")
        self.m = model.Model(**PARAMS)
        self.sfp_ok = True
        self.sfp = pick(dut, "sfp_tx_disable")

    async def start(self):
        cocotb.start_soon(Clock(self.c3, 40000, "ps").start())
        if self.ref is not None:
            cocotb.start_soon(Clock(self.ref, 6400, "ps").start())
        self.dut.h_we.value = 0
        self.dut.h_re.value = 0
        self.dut.h_addr.value = 0
        self.dut.h_wdata.value = 0
        await self.reset()

    async def reset(self):
        if self.rst is not None:
            self.rst.value = 1
        for _ in range(10):
            await self.cyc()
        if self.rst is not None:
            self.rst.value = 0
        self.m.reset()
        self.m.inp = {}
        for _ in range(6):
            await self.cyc()

    async def cyc(self, we=0, re=0, addr=0, wdata=0):
        self.dut.h_we.value = we
        self.dut.h_re.value = re
        self.dut.h_addr.value = addr
        self.dut.h_wdata.value = wdata
        await RisingEdge(self.c3)
        await Timer(1000, "ps")
        self.m.step({"h_we": we, "h_re": re, "h_addr": addr, "h_wdata": wdata})
        if self.sfp is not None and int(self.sfp.value) != 1:
            self.sfp_ok = False

    async def tick(self, n):
        for _ in range(n):
            await self.cyc()

    async def write(self, addr, val):
        await self.cyc(we=1, addr=addr, wdata=val)

    async def read(self, addr):
        await self.cyc(re=1, addr=addr)
        await self.cyc()
        await self.cyc()
        v = int(self.dut.h_rdata.value)
        return v

    async def check(self, addr, exp, what=""):
        v = await self.read(addr)
        assert v == exp, f"{what} reg 0x{addr:x}: got 0x{v:x} expected 0x{exp:x}"

    async def run_meas(self, gate, expect_ignored_writes=None):
        """Start a measurement and wait for DONE; return (count, actual, meas)."""
        await self.write(CTRL, 1)
        st = await self.read(STATUS)
        assert st & 1, f"BUSY not visible right after START, status {st:x}"
        assert not st & 2, "DONE not cleared by START"
        return await self.wait_done()

    async def wait_done(self, limit=3000):
        for _ in range(limit):
            st = await self.read(STATUS)
            busy, done = st & 1, (st >> 1) & 1
            assert busy ^ done or st == 0, f"busy/done inconsistent {st:x}"
            assert st < 4
            if done:
                c = await self.read(COUNT)
                a = await self.read(ACTUAL)
                n = await self.read(MEAS)
                st2 = await self.read(STATUS)
                assert st2 == 2, "DONE must stay 1, BUSY 0, while results are read"
                return c, a, n
        raise AssertionError("measurement never completed")

    def expect_count(self, latched):
        return (latched * 4 + 24) // 25


async def setup(dut):
    b = Bench(dut)
    await b.start()
    return b


# req: REQ-01, REQ-04, REQ-15, REQ-28, REQ-19
@cocotb.test()
async def test_reset_values(dut):
    b = await setup(dut)
    await b.check(ID, 0x20910001, "ID")
    await b.check(ID, b.m.read_reg(ID), "ID model")
    await b.check(SCRATCH, 0, "SCRATCH")
    await b.check(GATE_LEN, DEFAULT_GATE, "GATE_LEN")
    await b.check(CTRL, 0, "CTRL")
    await b.check(STATUS, 0, "STATUS")
    await b.check(COUNT, 0, "COUNT")
    await b.check(ACTUAL, 0, "ACTUAL")
    await b.check(MEAS, 0, "MEAS")
    assert int(dut.led.value) == 0
    await b.tick(100)
    assert int(dut.led.value) == 0, "LEDs must stay 0 until LED_EN"
    assert b.sfp_ok
    # second reset after activity
    await b.write(SCRATCH, 0x55)
    await b.write(GATE_LEN, 2000)
    await b.reset()
    await b.check(SCRATCH, 0, "SCRATCH after 2nd reset")
    await b.check(GATE_LEN, DEFAULT_GATE, "GATE_LEN after 2nd reset")


# req: REQ-03, REQ-24
@cocotb.test()
async def test_scratch_rw(dut):
    b = await setup(dut)
    for v in MASKS:
        await b.write(SCRATCH, v)
        # takes effect one clock after h_we: a read pulse in the very next cycle sees it
        await b.cyc(re=1, addr=SCRATCH)
        await b.cyc()
        await b.cyc()
        assert int(dut.h_rdata.value) == v
        await b.check(SCRATCH, v, "scratch")
    # back-to-back write then read
    await b.cyc(we=1, addr=SCRATCH, wdata=0x0F0F0F0F)
    await b.cyc(re=1, addr=SCRATCH)
    await b.cyc()
    await b.cyc()
    assert int(dut.h_rdata.value) == 0x0F0F0F0F
    await b.write(GATE_LEN, 0xFFFFFFFF)
    await b.check(GATE_LEN, 0xFFFFFFFF, "gate_len max")
    await b.write(GATE_LEN, 0x55555555)
    await b.check(GATE_LEN, 0x55555555)
    await b.write(GATE_LEN, 0xAAAAAAAA)
    await b.check(GATE_LEN, 0xAAAAAAAA)
    await b.write(GATE_LEN, 3000)
    await b.check(GATE_LEN, 3000)


# req: REQ-22, REQ-23
@cocotb.test()
async def test_unmapped_and_ro(dut):
    b = await setup(dut)
    await b.write(SCRATCH, 0xCAFE0001)
    await b.write(GATE_LEN, 4321)
    for a in [0x00C, 0x01C + 0x0C, 0x028, 0x02C, 0x040, 0x100, 0x7FC, 0x800, 0xFFC, 0x014 + 0x400]:
        await b.write(a, 0xFFFFFFFF)
        await b.check(a, 0, "unmapped")
    for a in [ID, BUILD, STATUS, COUNT, ACTUAL, MEAS]:
        before = await b.read(a)
        await b.write(a, 0xFFFFFFFF)
        await b.check(a, before, "RO write ignored")
    await b.check(ID, 0x20910001)
    await b.check(SCRATCH, 0xCAFE0001, "scratch untouched")
    await b.check(GATE_LEN, 4321, "gate_len untouched")
    await b.check(CTRL, 0, "ctrl untouched")
    await b.check(STATUS, 0)
    assert int(dut.led.value) == 0
    # no measurement was started by the stray writes
    await b.tick(50)
    await b.check(MEAS, 0)


# req: REQ-21, REQ-29
@cocotb.test()
async def test_read_latency_hold(dut):
    b = await setup(dut)
    await b.write(SCRATCH, 0x13579BDF)
    await b.write(GATE_LEN, 1234)
    for addr, exp in [(SCRATCH, 0x13579BDF), (GATE_LEN, 1234), (ID, 0x20910001)]:
        await b.cyc(re=1, addr=addr)
        await b.cyc(addr=addr)
        await b.cyc(addr=addr)
        assert int(dut.h_rdata.value) == exp, "h_rdata not valid 2 clocks after h_re"
        # hold while the address bus moves and writes to other registers occur
        await b.cyc(we=1, addr=0x040, wdata=7)
        for k in range(5):
            await b.cyc(addr=0x100 + 4 * k)
            assert int(dut.h_rdata.value) == exp, "h_rdata must hold until next h_re"
    # a held value of a changing register is not refreshed without h_re
    await b.write(SCRATCH, 0x2222)
    await b.tick(4)
    v = int(dut.h_rdata.value)
    assert v == 1234 or v == 0x20910001, "h_rdata changed without h_re"


# req: REQ-05, REQ-07, REQ-08, REQ-09, REQ-10, REQ-11, REQ-27
@cocotb.test()
async def test_measure_basic(dut):
    b = await setup(dut)
    last_n = 0
    for gate in [1000, 2500, 1000]:
        await b.write(GATE_LEN, gate)
        c, a, n = await b.run_meas(gate)
        assert a == gate, f"GATE_ACTUAL {a} != {gate}"
        exp = b.expect_count(gate)
        assert abs(c - exp) <= 2, f"COUNT {c} expected about {exp}"
        # compare with the model
        for _ in range(2000):
            if b.m.done:
                break
            b.m.step()
        assert b.m.actual == a
        assert abs(b.m.count - c) <= 3, f"model COUNT {b.m.count} vs RTL {c}"
        assert n == last_n + 1, "MEAS_DONE must increment by exactly 1"
        last_n = n
        await b.check(CTRL, 0, "START reads back 0")
        # stable results while idle
        await b.tick(60)
        assert await b.read(COUNT) == c
        assert await b.read(ACTUAL) == a
        assert await b.read(MEAS) == n
        assert await b.read(STATUS) == 2
    # new start clears DONE, keeps COUNT/ACTUAL until the new result
    await b.write(GATE_LEN, 1000)
    await b.write(CTRL, 1)
    prev_c = c
    for _ in range(1000):
        st = await b.read(STATUS)
        if st & 2:
            break
        assert st == 1, f"status while busy {st:x}"
        assert await b.read(COUNT) == prev_c, "COUNT must keep last value until DONE"
        assert await b.read(MEAS) == last_n
    else:
        raise AssertionError("no done")
    assert await b.read(MEAS) == last_n + 1
    assert b.sfp_ok


# req: REQ-06, REQ-10, REQ-11
@cocotb.test()
async def test_start_while_busy(dut):
    b = await setup(dut)
    await b.write(GATE_LEN, 3000)
    await b.write(CTRL, 1)
    st = await b.read(STATUS)
    assert st == 1
    await b.write(CTRL, 1)        # ignored
    await b.write(GATE_LEN, 1000)  # stored but not used by the running measurement
    await b.write(CTRL, 1)
    await b.check(GATE_LEN, 1000)
    c, a, n = await b.wait_done()
    assert a == 3000, f"running measurement must use latched gate, got {a}"
    assert abs(c - b.expect_count(3000)) <= 2
    assert n == 1, "extra START while busy must not start a second measurement"
    await b.tick(1500)
    assert await b.read(STATUS) == 2
    assert await b.read(MEAS) == 1, "no hidden second measurement"
    # now a real second one uses the new GATE_LEN
    c, a, n = await b.run_meas(1000)
    assert a == 1000 and n == 2


# req: REQ-12
@cocotb.test()
async def test_gate_min_clamp(dut):
    b = await setup(dut)
    for g in [0, 1, 999, 1000, 1001]:
        await b.write(GATE_LEN, g)
        await b.check(GATE_LEN, g, "GATE_LEN reads back as written")
        c, a, n = await b.run_meas(g)
        lat = max(g, 1000)
        assert a == lat, f"gate {g}: GATE_ACTUAL {a} expected {lat}"
        assert abs(c - b.expect_count(lat)) <= 2


async def sample_leds(b, n):
    out = []
    for _ in range(n):
        await b.cyc()
        out.append(int(b.dut.led.value))
    return out


def intervals(seq, bit):
    last = None
    res = []
    prev = (seq[0] >> bit) & 1
    for i, v in enumerate(seq):
        x = (v >> bit) & 1
        if x != prev:
            if last is not None:
                res.append(i - last)
            last = i
            prev = x
    return res


# req: REQ-15, REQ-16, REQ-17, REQ-18
@cocotb.test()
async def test_leds(dut):
    b = await setup(dut)
    assert int(dut.led.value) == 0
    await b.write(CTRL, 2)
    await b.check(CTRL, 2, "LED_EN reads back")
    seq = await sample_leds(b, LED_C3_HALF * 12)
    i0 = intervals(seq, 0)
    assert len(i0) >= 8, f"led0 not toggling: {seq[:40]}"
    assert all(abs(i - LED_C3_HALF) <= 0 for i in i0), f"led0 intervals {i0}"
    i1 = intervals(seq, 1)
    exp1 = LED_REF_HALF * 6.4 / 40.0
    assert len(i1) >= 8, f"led1 not toggling: {i1}"
    avg = sum(i1) / len(i1)
    assert abs(avg - exp1) <= 1.0, f"led1 half period {avg} c3 cycles, expected {exp1}"
    assert all(abs(i - exp1) <= 2 for i in i1), f"led1 intervals {i1}"
    # clearing LED_EN forces both LEDs to 0, and they stay 0
    await b.write(CTRL, 0)
    await b.tick(6)
    assert int(dut.led.value) == 0
    seq = await sample_leds(b, 100)
    assert all(v == 0 for v in seq), "LEDs must stay 0 with LED_EN 0"
    # re-enable works, and a measurement does not disturb LED_EN when written with bit1
    await b.write(GATE_LEN, 1000)
    await b.write(CTRL, 3)
    c, a, n = await b.wait_done()
    assert a == 1000
    seq = await sample_leds(b, LED_C3_HALF * 4)
    assert any(v & 1 for v in seq), "led0 toggles after re-enable"
    assert b.sfp_ok


# req: REQ-19
@cocotb.test()
async def test_sfp_constant(dut):
    b = await setup(dut)
    assert b.sfp is not None
    await b.write(CTRL, 3)
    for i in range(300):
        await b.cyc()
        assert int(b.sfp.value) == 1
    await b.reset()
    assert int(b.sfp.value) == 1
    assert b.sfp_ok


# req: REQ-03, REQ-05, REQ-06, REQ-08, REQ-09, REQ-10, REQ-12, REQ-18, REQ-22, REQ-23
@cocotb.test()
async def test_random_traffic(dut):
    b = await setup(dut)
    rnd = random.Random(int(getattr(cocotb, "RANDOM_SEED", 1)))
    scratch = 0
    gate = DEFAULT_GATE
    meas = 0
    led_en = 0
    for it in range(60):
        op = rnd.choice(["scr", "scr", "gate", "ro", "unm", "rd", "meas", "meas", "led"])
        if op == "scr":
            scratch = rnd.choice(MASKS + [rnd.getrandbits(32)])
            await b.write(SCRATCH, scratch)
            await b.check(SCRATCH, scratch)
        elif op == "gate":
            gate = rnd.choice([0, 999, 1000, 1001, 1500, 2000, rnd.getrandbits(32)])
            await b.write(GATE_LEN, gate)
            await b.check(GATE_LEN, gate)
        elif op == "ro":
            a = rnd.choice([ID, BUILD, STATUS, COUNT, ACTUAL, MEAS])
            before = await b.read(a)
            await b.write(a, rnd.getrandbits(32))
            await b.check(a, before)
        elif op == "unm":
            a = rnd.choice([0xC, 0x28, 0x2C, 0x30, 0x80, 0x3FC, 0xFFC, 0x44])
            await b.write(a, rnd.getrandbits(32))
            await b.check(a, 0)
        elif op == "rd":
            a = rnd.choice([ID, SCRATCH, GATE_LEN, CTRL])
            await b.check(a, b.m.read_reg(a))
        elif op == "led":
            led_en = rnd.getrandbits(1)
            await b.write(CTRL, led_en << 1)
            await b.check(CTRL, led_en << 1)
            await b.tick(8)
            if not led_en:
                assert int(dut.led.value) == 0
        elif op == "meas":
            g = rnd.choice([1000, 1000, 1200, 1700])
            await b.write(GATE_LEN, g)
            gate = g
            await b.write(CTRL, 1 | (led_en << 1))
            if rnd.random() < 0.5:
                await b.write(CTRL, 1 | (led_en << 1))  # ignored while busy
            c, a, n = await b.wait_done()
            meas += 1
            assert a == g
            assert abs(c - b.expect_count(g)) <= 2
            assert n == meas
    await b.check(SCRATCH, scratch)
    assert b.sfp_ok
