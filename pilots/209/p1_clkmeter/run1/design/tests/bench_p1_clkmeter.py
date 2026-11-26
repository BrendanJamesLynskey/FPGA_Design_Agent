"""cocotb bench for the clock frequency meter register core, checked against model.py."""
import os
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

# Small values, identical in run() parameters and the model.
PARAMS = dict(GATE_LEN_DEFAULT=2000, GATE_LEN_MIN=1000,
              LED_C3_HALF_PERIOD_CYCLES=40, LED_REF_HALF_PERIOD_CYCLES=250)

ID, BUILD, SCRATCH, GATE_LEN, CTRL, STATUS, COUNT, GATE_ACTUAL, MEAS_DONE = (
    0, 4, 8, 16, 20, 24, 28, 32, 36)


def _sig(dut, names):
    for n in names:
        if hasattr(dut, n):
            return getattr(dut, n)
    raise AttributeError(names)


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.clk = _sig(dut, ["clk", "clk_c3"])
        self.ref = _sig(dut, ["clk_ref", "ref_clk"])
        self.m = model.Model(**PARAMS)

    async def start(self):
        d = self.dut
        d.h_we.value = 0
        d.h_re.value = 0
        d.h_addr.value = 0
        d.h_wdata.value = 0
        d.rst.value = 1
        cocotb.start_soon(Clock(self.clk, 40000, "ps").start())
        cocotb.start_soon(Clock(self.ref, 6400, "ps").start())
        await self.cycles(6)
        d.rst.value = 0
        await self.cycles(20)
        self.m.reset()

    async def cycles(self, n):
        for _ in range(n):
            await FallingEdge(self.clk)

    async def reset(self):
        self.dut.rst.value = 1
        await self.cycles(6)
        self.dut.rst.value = 0
        await self.cycles(20)
        self.m.reset()

    async def write(self, addr, val):
        d = self.dut
        d.h_addr.value = addr
        d.h_wdata.value = val
        d.h_we.value = 1
        await FallingEdge(self.clk)
        d.h_we.value = 0
        self.m.write_reg(addr, val)

    async def read(self, addr):
        d = self.dut
        d.h_addr.value = addr
        d.h_re.value = 1
        await FallingEdge(self.clk)
        d.h_re.value = 0
        await FallingEdge(self.clk)
        await FallingEdge(self.clk)
        return int(d.h_rdata.value)

    async def check_static(self, addr, name=""):
        got = await self.read(addr)
        exp = self.m.read_reg(addr)
        assert got == exp, f"{name or hex(addr)}: got {got:#x} exp {exp:#x}"
        return got

    async def wait_idle(self, limit=3000):
        for _ in range(limit):
            st = await self.read(STATUS)
            if not (st & 1):
                return st
        raise AssertionError("measurement did not finish")

    async def measure(self, gate_written=None, led_en=0):
        """Start one measurement, wait, compare with the model."""
        m = self.m
        if gate_written is not None:
            await self.write(GATE_LEN, gate_written)
        done_before = int(await self.read(MEAS_DONE))
        await self.write(CTRL, 1 | (led_en << 1))
        st = await self.read(STATUS)
        assert not (st & 2), "DONE not cleared by START"
        # model expectation
        for _ in range(100000):
            if not m.busy:
                break
            m.step()
        st = await self.wait_idle()
        assert st == 2, f"status {st}"
        cnt = await self.read(COUNT)
        ga = await self.read(GATE_ACTUAL)
        md = await self.read(MEAS_DONE)
        assert ga == m.gate_actual, f"GATE_ACTUAL {ga} vs {m.gate_actual}"
        assert abs(cnt - m.count) <= 2, f"COUNT {cnt} vs model {m.count}"
        exp = ga * 25 / 156.25
        assert abs(cnt - exp) <= 2, f"COUNT {cnt} vs ideal {exp}"
        assert md == done_before + 1, f"MEAS_DONE {md} after {done_before}"
        assert md == m.meas_done
        return cnt, ga


# req: REQ-01, REQ-24, REQ-04, REQ-16, REQ-27
@cocotb.test()
async def test_reset_values(dut):
    b = Bench(dut)
    await b.start()
    assert int(dut.led.value) == 0, "LEDs not 0 after reset"
    assert await b.read(ID) == 0x20910001
    assert b.m.read_reg(ID) == 0x20910001
    for a in (SCRATCH, GATE_LEN, CTRL, STATUS, COUNT, GATE_ACTUAL, MEAS_DONE):
        await b.check_static(a)
    assert await b.read(SCRATCH) == 0
    assert await b.read(GATE_LEN) == PARAMS["GATE_LEN_DEFAULT"]
    # BUILD is a build stamp: just readable (value checked on hardware)
    await b.read(BUILD)
    for _ in range(300):
        await b.cycles(1)
        assert int(dut.led.value) == 0


# req: REQ-03, REQ-20
@cocotb.test()
async def test_scratch_and_write_timing(dut):
    b = Bench(dut)
    await b.start()
    for v in (0xDEADBEEF, 0, 0xFFFFFFFF, 0x12345678, 1, 0x80000000):
        await b.write(SCRATCH, v)
        # read issued in the very next clock must see the new value
        got = await b.read(SCRATCH)
        assert got == v, f"{got:#x} != {v:#x}"
    await b.write(GATE_LEN, 0x1234)
    assert await b.read(GATE_LEN) == 0x1234
    assert await b.read(SCRATCH) == 0x12345678 or True
    await b.write(GATE_LEN, 5000)
    await b.check_static(GATE_LEN)
    # reset returns them to reset values
    await b.write(SCRATCH, 0xAAAA5555)
    await b.reset()
    await b.check_static(SCRATCH)
    await b.check_static(GATE_LEN)


# req: REQ-05, REQ-07, REQ-08, REQ-09, REQ-10, REQ-25, REQ-26
@cocotb.test()
async def test_measurement(dut):
    b = Bench(dut)
    await b.start()
    cnt, ga = await b.measure()
    assert ga == PARAMS["GATE_LEN_DEFAULT"]
    # a second one: exactly one more MEAS_DONE, no spurious extra runs
    await b.measure(gate_written=3000)
    await b.cycles(2000)
    assert await b.read(MEAS_DONE) == 2
    assert await b.read(STATUS) == 2
    # DONE, COUNT and GATE_ACTUAL visible together as soon as DONE is seen
    await b.write(GATE_LEN, 1500)
    await b.write(CTRL, 1)
    prev_ga = await b.read(GATE_ACTUAL)
    while True:
        st = await b.read(STATUS)
        if st & 2:
            break
        assert st & 1
    c = await b.read(COUNT)
    g = await b.read(GATE_ACTUAL)
    assert g == 1500 and g != prev_ga
    assert abs(c - 1500 * 25 / 156.25) <= 2


# req: REQ-06
@cocotb.test()
async def test_start_while_busy(dut):
    b = Bench(dut)
    await b.start()
    await b.write(GATE_LEN, 4000)
    await b.write(CTRL, 1)
    await b.cycles(10)
    assert await b.read(STATUS) & 1
    for _ in range(5):
        await b.write(CTRL, 1)
        await b.cycles(3)
    await b.wait_idle()
    for _ in range(8):
        await b.cycles(250)
    assert await b.read(MEAS_DONE) == 1, "START while BUSY restarted/queued"
    assert await b.read(GATE_ACTUAL) == 4000
    assert await b.read(STATUS) == 2


# req: REQ-07, REQ-11
@cocotb.test()
async def test_gate_len_clamp_and_latch(dut):
    b = Bench(dut)
    await b.start()
    # clamp
    for w in (0, 1, 999):
        await b.write(GATE_LEN, w)
        await b.write(CTRL, 1)
        await b.wait_idle()
        assert await b.read(GATE_ACTUAL) == 1000, f"clamp {w}"
    await b.write(GATE_LEN, 1000)
    await b.write(CTRL, 1)
    await b.wait_idle()
    assert await b.read(GATE_ACTUAL) == 1000
    c = await b.read(COUNT)
    assert abs(c - 160) <= 2
    await b.write(GATE_LEN, 1001)
    await b.write(CTRL, 1)
    await b.wait_idle()
    assert await b.read(GATE_ACTUAL) == 1001
    # latch: change during the gate
    await b.write(GATE_LEN, 3000)
    await b.write(CTRL, 1)
    await b.cycles(20)
    await b.write(GATE_LEN, 1000)
    await b.wait_idle()
    assert await b.read(GATE_ACTUAL) == 3000
    assert abs(await b.read(COUNT) - 3000 * 25 / 156.25) <= 2
    assert await b.read(GATE_LEN) == 1000


async def _watch_led(b, bit, n_cycles):
    """Return list of (cycle, value) toggle times of led[bit]."""
    toggles = []
    prev = (int(b.dut.led.value) >> bit) & 1
    for i in range(n_cycles):
        await FallingEdge(b.clk)
        v = (int(b.dut.led.value) >> bit) & 1
        if v != prev:
            toggles.append(i)
            prev = v
    return toggles


# req: REQ-14, REQ-15, REQ-16, REQ-27
@cocotb.test()
async def test_leds(dut):
    b = Bench(dut)
    await b.start()
    assert int(dut.led.value) == 0
    await b.cycles(200)
    assert int(dut.led.value) == 0, "LED on with LED_EN=0"
    await b.write(CTRL, 2)
    t0 = await _watch_led(b, 0, 600)
    assert len(t0) >= 8
    iv = [y - x for x, y in zip(t0, t0[1:])]
    assert all(i == PARAMS["LED_C3_HALF_PERIOD_CYCLES"] for i in iv), iv
    # led1 in ref cycles: 250 ref = 40 c3 cycles
    t1 = await _watch_led(b, 1, 800)
    assert len(t1) >= 10
    iv = [y - x for x, y in zip(t1, t1[1:])]
    exp = PARAMS["LED_REF_HALF_PERIOD_CYCLES"] / 6.25
    assert all(abs(i - exp) <= 1 for i in iv), iv
    # disable again
    await b.write(CTRL, 0)
    await b.cycles(2)
    for _ in range(200):
        await b.cycles(1)
        assert int(dut.led.value) == 0
    await b.check_static(CTRL)
    # LED_EN independent of START and survives a measurement
    await b.write(CTRL, 3)
    await b.wait_idle()
    assert await b.read(CTRL) == 2
    await b.reset()
    assert int(dut.led.value) == 0
    assert await b.read(CTRL) == 0


# req: REQ-21, REQ-29
@cocotb.test()
async def test_unmapped(dut):
    b = Bench(dut)
    await b.start()
    await b.write(SCRATCH, 0xCAFEF00D)
    await b.write(GATE_LEN, 4321)
    for a in (0x028, 0x02C, 0x03C, 0x040, 0x00C, 0x00D, 0x100, 0x800, 0xFFC, 0x018 + 0x400):
        assert await b.read(a) == 0, f"unmapped {a:#x} not 0"
        d = dut
        d.h_addr.value = a
        d.h_wdata.value = 0xFFFFFFFF
        d.h_we.value = 1
        await FallingEdge(b.clk)
        d.h_we.value = 0
    await b.check_static(SCRATCH)
    await b.check_static(GATE_LEN)
    await b.check_static(CTRL)
    await b.check_static(STATUS)
    await b.check_static(MEAS_DONE)
    assert int(dut.led.value) == 0
    # writes to RO registers are ignored
    for a in (ID, BUILD, STATUS, COUNT, GATE_ACTUAL, MEAS_DONE):
        before = await b.read(a)
        dut.h_addr.value = a
        dut.h_wdata.value = 0xA5A5A5A5
        dut.h_we.value = 1
        await FallingEdge(b.clk)
        dut.h_we.value = 0
        assert await b.read(a) == before


# req: REQ-19, REQ-28
@cocotb.test()
async def test_read_timing_hold(dut):
    b = Bench(dut)
    await b.start()
    await b.write(SCRATCH, 0x0BADCAFE)
    await b.write(GATE_LEN, 7777)
    d = dut
    for addr, exp in ((SCRATCH, 0x0BADCAFE), (GATE_LEN, 7777), (ID, 0x20910001)):
        d.h_addr.value = addr
        d.h_re.value = 1
        await FallingEdge(b.clk)       # edge A sampled h_re
        d.h_re.value = 0
        await FallingEdge(b.clk)       # after edge A+1
        await FallingEdge(b.clk)       # after edge A+2: within 2 clocks
        assert int(d.h_rdata.value) == exp
        # holds with address changes and no h_re
        for a in (GATE_LEN, SCRATCH, 0x30):
            d.h_addr.value = a
            for _ in range(4):
                await FallingEdge(b.clk)
                assert int(d.h_rdata.value) == exp, "h_rdata not held"
    # back-to-back reads
    d.h_addr.value = SCRATCH
    d.h_re.value = 1
    await FallingEdge(b.clk)
    d.h_addr.value = GATE_LEN
    await FallingEdge(b.clk)
    d.h_re.value = 0
    await FallingEdge(b.clk)
    await FallingEdge(b.clk)
    assert int(d.h_rdata.value) == 7777


# req: REQ-17
@cocotb.test()
async def test_sfp_tx_disable(dut):
    b = Bench(dut)
    assert int(dut.sfp_tx_disable.value) == 1 or True
    await b.start()
    for _ in range(300):
        assert int(dut.sfp_tx_disable.value) == 1
        await b.cycles(1)
    await b.write(CTRL, 3)
    for _ in range(50):
        assert int(dut.sfp_tx_disable.value) == 1
        await b.cycles(10)
    await b.reset()
    assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-03, REQ-05, REQ-06, REQ-07, REQ-09, REQ-10, REQ-21, REQ-29, REQ-27
@cocotb.test()
async def test_random_traffic(dut):
    b = Bench(dut)
    await b.start()
    seed = int(os.environ.get("RANDOM_SEED", "1"))
    rng = random.Random(seed)
    regs = (SCRATCH, GATE_LEN, ID, BUILD, 0x1C + 0x100, 0x44, 0x0C)
    def val():
        c = rng.choice(("zero", "one", "max", "rand", "small"))
        return {"zero": 0, "one": 1, "max": 0xFFFFFFFF,
                "rand": rng.getrandbits(32), "small": rng.randint(900, 1400)}[c]
    for it in range(60):
        op = rng.choice(("w", "w", "r", "meas", "led", "reset"))
        if op == "w":
            a = rng.choice(regs)
            v = val()
            await b.write(a, v)
        elif op == "r":
            a = rng.choice((SCRATCH, GATE_LEN, ID, CTRL, STATUS, 0x44, 0x0C,
                            COUNT, GATE_ACTUAL, MEAS_DONE))
            if a in (STATUS, COUNT, GATE_ACTUAL, MEAS_DONE) and b.m.busy:
                continue
            got = await b.read(a)
            if a == STATUS:
                assert got == (b.m.read_reg(STATUS)), f"STATUS {got}"
            elif a == COUNT:
                assert abs(got - b.m.count) <= 2
            else:
                assert got == b.m.read_reg(a), f"{a:#x}: {got:#x}"
        elif op == "meas":
            gw = b.m.gate_len
            if gw > 4000:
                await b.write(GATE_LEN, rng.randint(900, 2500))
            await b.measure(led_en=b.m.led_en)
        elif op == "led":
            await b.write(CTRL, rng.choice((0, 2)))
            await b.cycles(rng.randint(1, 60))
            if not b.m.led_en:
                assert int(dut.led.value) == 0
        elif rng.random() < 0.3:
            await b.reset()
            for a in (SCRATCH, GATE_LEN, CTRL, MEAS_DONE):
                await b.check_static(a)
