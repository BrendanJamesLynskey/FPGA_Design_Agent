"""cocotb bench for c14_int8_dot_requant_top: every check is a comparison with model.Model."""
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import ClockCycles, RisingEdge, Timer  # noqa: E402
from cocotb_coverage.coverage import CoverPoint, coverage_db  # noqa: E402

# Must equal the parameters given to flow.cocotb_run.run in the pytest entry.
CPB = 8
TIMEOUT = 2000
BUILD = 0x1BADB002
MASK32 = 0xFFFFFFFF

CMD_READ = 1
CMD_WRITE = 2


# ---------------------------------------------------------------- coverage
@CoverPoint("top.clamp_class", xf=lambda c: c,
            bins=["neg_sat", "pos_sat", "relu_floor", "in_range", "edge_hi", "edge_lo"])
def cov_clamp(c):
    pass


@CoverPoint("top.shift_class", xf=lambda c: c, bins=["s1", "mid", "s31"])
def cov_shift(c):
    pass


@CoverPoint("top.relu", xf=lambda c: c, bins=[0, 1])
def cov_relu(c):
    pass


@CoverPoint("top.mult_class", xf=lambda c: c, bins=["zero", "one", "max", "other"])
def cov_mult(c):
    pass


@CoverPoint("top.acc_class", xf=lambda c: c, bins=["min", "neg", "zero", "pos", "max"])
def cov_acc(c):
    pass


@CoverPoint("top.round_class", xf=lambda c: c, bins=["half", "neg_half", "nonhalf"])
def cov_round(c):
    pass


@CoverPoint("top.reg_access", xf=lambda c: c,
            bins=[f"rd_{i}" for i in range(11)] + ["rd_unmapped"] +
            [f"wr_{i}" for i in range(8)] + ["wr_ro", "wr_unmapped"])
def cov_reg(c):
    pass


@CoverPoint("top.go_class", xf=lambda c: c, bins=["first", "restart"])
def cov_go(c):
    pass


@CoverPoint("top.rst_class", xf=lambda c: c, bins=["with_result", "idle", "mid_compute"])
def cov_rst(c):
    pass


def s32(v):
    v &= MASK32
    return v - (1 << 32) if v & 0x80000000 else v


def pack(vals):
    lo = hi = 0
    for i in range(4):
        lo |= (vals[i] & 0xFF) << (8 * i)
        hi |= (vals[4 + i] & 0xFF) << (8 * i)
    return lo, hi


def L(*v):
    return list(v) + [0] * (8 - len(v))


def sample_case(m):
    acc = s32(m.read_reg(9))
    mult = m.read_reg(5) & 0xFFFF
    ctrl = m.read_reg(6)
    shift = ctrl & 0x1F
    relu = (ctrl >> 8) & 1
    prod = acc * mult
    scaled = (prod + (1 << (shift - 1))) >> shift
    if relu:
        if scaled < 0:
            c = "relu_floor"
        elif scaled > 127:
            c = "pos_sat"
        elif scaled == 127:
            c = "edge_hi"
        else:
            c = "in_range"
    else:
        if scaled > 127:
            c = "pos_sat"
        elif scaled == 127:
            c = "edge_hi"
        elif scaled < -128:
            c = "neg_sat"
        elif scaled == -128:
            c = "edge_lo"
        else:
            c = "in_range"
    cov_clamp(c)
    cov_shift("s1" if shift == 1 else "s31" if shift == 31 else "mid")
    cov_relu(relu)
    cov_mult("zero" if mult == 0 else "one" if mult == 1 else "max" if mult == 65535 else "other")
    if acc == -(1 << 31):
        a = "min"
    elif acc == (1 << 31) - 1:
        a = "max"
    elif acc < 0:
        a = "neg"
    elif acc == 0:
        a = "zero"
    else:
        a = "pos"
    cov_acc(a)
    rem = prod % (1 << shift)
    if rem == (1 << (shift - 1)):
        cov_round("neg_half" if prod < 0 else "half")
    else:
        cov_round("nonhalf")


# ---------------------------------------------------------------- protocol
def xor8(bs):
    r = 0
    for b in bs:
        r ^= b
    return r


def frame(cmd, addr, data=0, bad_chk=False):
    body = bytes([cmd, addr]) + (data & MASK32).to_bytes(4, "little")
    chk = xor8(body)
    if bad_chk:
        chk ^= 0x55
    return bytes([0xA5]) + body + bytes([chk])


def bit_of(sig, default):
    try:
        return int(sig.value)
    except (ValueError, TypeError):
        return default


class Env:
    def __init__(self, dut):
        self.dut = dut
        self.clk = dut.CLK100MHZ
        self.m = model.Model(CLKS_PER_BIT=CPB, TIMEOUT_CYCLES=TIMEOUT, BUILD_STAMP=BUILD)
        self.rx = []
        self.runs = []
        self.led_events = []
        self.frame_err = 0
        self.cyc = 0
        self.last_t0 = []
        seed = getattr(cocotb, "RANDOM_SEED", None)
        if seed is None:
            seed = int(os.environ.get("RANDOM_SEED", "1"))
        self.rng = random.Random(seed)

    # -- clocks, reset, monitor
    async def start(self):
        d = self.dut
        try:
            clk = Clock(self.clk, 10, unit="ns")
        except TypeError:
            clk = Clock(self.clk, 10, units="ns")
        cocotb.start_soon(clk.start())
        d.UART_TXD_IN.value = 1
        d.CPU_RESETN.value = 0
        await ClockCycles(self.clk, 3)
        cocotb.start_soon(self.monitor())
        await ClockCycles(self.clk, 5)
        d.CPU_RESETN.value = 1
        await self.after_reset()

    async def after_reset(self):
        await ClockCycles(self.clk, 15 * CPB)
        self.m.reset()
        self.rx.clear()
        self.frame_err = 0

    async def hw_reset(self, hold=6):
        self.dut.CPU_RESETN.value = 0
        await ClockCycles(self.clk, hold)
        self.dut.CPU_RESETN.value = 1
        await self.after_reset()

    async def monitor(self):
        d = self.dut
        state = 0
        cnt = 0
        cur = 0
        t0 = 0
        run = 0
        run_start = 0
        last_led = None
        while True:
            await RisingEdge(self.clk)
            self.cyc += 1
            lv = bit_of(d.LED0, -1)
            if lv != -1:
                if last_led is not None and lv != last_led:
                    self.led_events.append((self.cyc, lv))
                last_led = lv
            v = bit_of(d.UART_RXD_OUT, 1)
            if v == 0:
                if run == 0:
                    run_start = self.cyc
                run += 1
            elif run:
                self.runs.append((run_start, run))
                run = 0
            if state == 0:
                if v == 0:
                    state = 1
                    cnt = 0
                    cur = 0
                    t0 = self.cyc
            else:
                cnt += 1
                if cnt % CPB == CPB // 2:
                    k = cnt // CPB
                    if k == 0:
                        if v != 0:
                            state = 0
                    elif k <= 8:
                        cur |= v << (k - 1)
                    else:
                        if v != 1:
                            self.frame_err += 1
                        self.rx.append((cur, t0))
                        state = 0

    # -- uart
    async def bit(self, v):
        self.dut.UART_TXD_IN.value = v
        await ClockCycles(self.clk, CPB)

    async def send(self, bs):
        for b in bs:
            await self.bit(0)
            for i in range(8):
                await self.bit((b >> i) & 1)
            await self.bit(1)

    async def recv(self, n=7):
        t = 0
        limit = 150 * CPB
        while len(self.rx) < n:
            await RisingEdge(self.clk)
            t += 1
            assert t < limit, f"no response ({len(self.rx)} of {n} bytes)"
        items = self.rx[:n]
        del self.rx[:n]
        self.last_t0 = [t0 for _, t0 in items]
        return [b for b, _ in items]

    async def txn(self, cmd, addr, data=0, bad_chk=False):
        assert not self.rx, f"unexpected bytes from the shell: {self.rx}"
        self.frame_err = 0
        await self.send(frame(cmd, addr, data, bad_chk))
        raw = await self.recv(7)
        await ClockCycles(self.clk, 2 * CPB)
        assert self.frame_err == 0, "stop bit error on response"
        assert raw[0] == 0x5A, f"bad response sync {raw}"
        assert xor8(raw[1:6]) == raw[6], f"bad response checksum {raw}"
        return raw[1], int.from_bytes(bytes(raw[2:6]), "little")

    # -- model-checked register access
    def check_led(self):
        led = bit_of(self.dut.LED0, -1)
        exp = self.m.read_reg(10)
        assert led == exp, f"LED0={led}, model ready={exp}"

    async def wreg(self, off, val):
        if off <= 7:
            cov_reg(f"wr_{off}")
        elif off <= 10:
            cov_reg("wr_ro")
        else:
            cov_reg("wr_unmapped")
        st, _ = await self.txn(CMD_WRITE, 0x80 + off, val & MASK32)
        assert st == 0, f"write window {off:#x} status {st}"
        self.m.write_reg(off, val & MASK32)
        if off == 7:
            for _ in range(10):
                self.m.step()
        self.check_led()

    async def rreg(self, off):
        st, data = await self.txn(CMD_READ, 0x80 + off)
        assert st == 0, f"read window {off:#x} status {st}"
        exp = self.m.read_reg(off)
        assert data == exp, f"reg {off:#x}: rtl {data:#x} model {exp:#x}"
        self.check_led()
        cov_reg(f"rd_{off}" if off <= 10 else "rd_unmapped")
        return data

    async def go(self, val=0):
        prev = self.m.read_reg(10)
        mark = len(self.led_events)
        await self.wreg(7, val)
        ev = self.led_events[mark:]
        if prev:
            assert len(ev) == 2 and ev[0][1] == 0 and ev[1][1] == 1, f"LED events on restart: {ev}"
            width = ev[1][0] - ev[0][0]
            assert 1 <= width <= 8, f"READY low for {width} cycles"
            cov_go("restart")
        else:
            assert len(ev) == 1 and ev[0][1] == 1, f"LED events on first go: {ev}"
            cov_go("first")

    async def run_case(self, act, wgt, bias, mult, shift, relu, go_val=0):
        alo, ahi = pack(act)
        wlo, whi = pack(wgt)
        ctrl = (shift & 0x1F) | ((relu & 1) << 8)
        for off, val in ((0, alo), (1, ahi), (2, wlo), (3, whi), (4, bias & MASK32),
                         (5, mult & 0xFFFF), (6, ctrl)):
            if self.m.read_reg(off) != val:
                await self.wreg(off, val)
        await self.go(go_val)
        y = await self.rreg(8)
        acc = await self.rreg(9)
        sample_case(self.m)
        return y, acc


Z = [0] * 8

CASES_A = [
    ([-128] * 8, [-127] * 8, 0, 1, 1, 0),
    ([127] * 8, [-127] * 8, 0, 1, 1, 0),
    ([127] * 8, [-127] * 8, 0, 1, 1, 1),
    (L(5), L(1), 0, 1, 1, 0),
    (L(-5), L(1), 0, 1, 1, 0),
    ([-128] * 8, [-127] * 8, 2147483647 - 130048, 65535, 31, 0),
    ([127] * 8, [-127] * 8, -2147483648 + 129032, 65535, 31, 0),
    (Z, Z, 0, 1, 1, 0),
    (L(1, 2, 3, 4, 5, 6, 7, 8), L(-1, 2, -3, 4, -5, 6, -7, 8), 7, 0, 5, 0),
]

CASES_B = [
    (Z, Z, 254, 1, 1, 0),
    (Z, Z, 255, 1, 1, 0),
    (Z, Z, -256, 1, 1, 0),
    (Z, Z, -257, 1, 1, 0),
    (Z, Z, -258, 1, 1, 0),
    (L(10), L(10), 0, 1, 1, 1),
    (L(100, 100, 100), L(1, 1, 1), 0, 1, 1, 1),
    (Z, Z, 0x40000000, 1, 31, 0),
    (Z, Z, -0x40000000, 1, 31, 0),
    (Z, Z, 1, 65535, 16, 0),
    (Z, Z, -1, 1, 1, 0),
    (Z, Z, 3, 1, 2, 0),
    (Z, Z, -3, 1, 2, 0),
    ([-128, 127, -128, 127, 127, -128, 0, 1], [127, -127, -127, 127, -1, 1, 5, -127], 12345, 1000, 10, 0),
    (L(0, 0, 0, 0, 0, 0, 0, -128), L(0, 0, 0, 0, 0, 0, 0, 127), 0, 3, 3, 0),
    (L(0, 0, 0, 0, 77, 0, 0, 0), L(0, 0, 0, 0, 3, 0, 0, 0), -50, 100, 8, 1),
]


def rand_case(rng):
    act = [rng.choice([-128, 127, 0, 1, -1, rng.randint(-128, 127), rng.randint(-128, 127)])
           for _ in range(8)]
    wgt = [rng.choice([-127, 127, 0, 1, -1, rng.randint(-127, 127), rng.randint(-127, 127)])
           for _ in range(8)]
    kind = rng.choice(["zero", "small", "big", "edge", "tiny"])
    if kind == "tiny":
        act = [rng.randint(-3, 3) for _ in range(8)]
        wgt = [rng.randint(-3, 3) for _ in range(8)]
    prod = sum(a * w for a, w in zip(act, wgt))
    lo = max(-(1 << 31), -(1 << 31) - prod)
    hi = min((1 << 31) - 1, (1 << 31) - 1 - prod)
    if kind == "zero":
        bias = 0
    elif kind in ("small", "tiny"):
        bias = rng.randint(-300, 300)
    elif kind == "big":
        bias = rng.randint(-(1 << 31), (1 << 31) - 1)
    else:
        bias = rng.choice([lo, hi])
    bias = max(lo, min(hi, bias))
    mult = rng.choice([0, 1, 65535, rng.randint(0, 65535), rng.randint(1, 255)])
    shift = rng.choice([1, 31, rng.randint(1, 31), rng.randint(1, 31), rng.randint(1, 12)])
    relu = rng.randint(0, 1)
    return act, wgt, bias, mult, shift, relu


# ---------------------------------------------------------------- tests
@cocotb.test()
async def test_smoke(dut):
    e = Env(dut)
    await e.start()
    assert bit_of(dut.LED0, -1) == 0
    assert bit_of(dut.UART_RXD_OUT, -1) == 1
    st, d = await e.txn(CMD_READ, 0x00)
    assert (st, d) == (0, 0x444F5451), f"DESIGN_ID {st} {d:#x}"
    st, d = await e.txn(CMD_READ, 0x01)
    assert (st, d) == (0, 0x00010000)
    st, d = await e.txn(CMD_READ, 0x02)
    assert (st, d) == (0, BUILD)
    for off in range(11):
        await e.rreg(off)
    assert (await e.rreg(6)) == 1
    await e.rreg(0x0B)
    await e.run_case(L(3, -4), L(5, 6), 10, 1, 1, 0)
    assert (await e.rreg(10)) == 1
    assert (await e.rreg(8)) == (((3 * 5 - 4 * 6 + 10) + 1) >> 1) & 0xFF
    assert (await e.rreg(9)) == (3 * 5 - 4 * 6 + 10) & MASK32
    assert bit_of(dut.LED0, -1) == 1


@cocotb.test()
async def test_regs_rw(dut):
    e = Env(dut)
    await e.start()
    pats = [0xFFFFFFFF, 0xA5A5A5A5, 0x5A5A5A5A, 0x80000001]
    masks = {0: MASK32, 1: MASK32, 2: MASK32, 3: MASK32, 4: MASK32, 5: 0xFFFF, 6: 0x11F}
    for off in range(7):
        for p in pats[:2] if off != 6 else pats:
            await e.wreg(off, p)
            got = await e.rreg(off)
            assert got == p & masks[off], f"reg {off} wrote {p:#x} read {got:#x}"
    await e.wreg(6, 1)
    await e.wreg(5, 0)
    # GO reads 0; RO registers ignore writes
    await e.rreg(7)
    await e.run_case(L(9, 8), L(7, 6), 5, 3, 2, 0)
    await e.wreg(7, 0xFFFFFFFF)  # restarts, same operands
    for off in (8, 9, 10):
        before = await e.rreg(off)
        await e.wreg(off, 0xFFFFFFFF)
        after = await e.rreg(off)
        assert before == after
    await e.rreg(7)


ALIASES = [0x0B, 0x0C, 0x0D, 0x0F, 0x10, 0x17, 0x20, 0x27, 0x30, 0x40, 0x41, 0x42, 0x43, 0x44,
           0x45, 0x46, 0x47, 0x48, 0x49, 0x4A, 0x7F]


@cocotb.test()
async def test_alias_unmapped(dut):
    e = Env(dut)
    await e.start()
    for off, val in ((0, 0x01020304), (1, 0x7F80FF01), (2, 0x05060708), (3, 0x81818181),
                     (4, 0x00001234), (5, 0x0000ABCD), (6, 0x00000103)):
        await e.wreg(off, val)
    for off in ALIASES:
        await e.wreg(off, (0x89ABCDEF ^ (off * 0x01010101)) & MASK32)
    for off in range(11):
        await e.rreg(off)
    for off in (0x0B, 0x0F, 0x10, 0x20, 0x40, 0x47, 0x4A, 0x5F, 0x7F):
        got = await e.rreg(off)
        assert got == 0
    # ready must still be clear: no alias started a computation
    assert bit_of(dut.LED0, -1) == 0
    await e.go()
    for off in (8, 9, 10):
        await e.rreg(off)
    for off in (0x48, 0x49, 0x4A, 0x08, 0x09, 0x0A):
        await e.wreg(off, 0xFFFFFFFF)
    for off in (8, 9, 10, 0, 6):
        await e.rreg(off)


@cocotb.test()
async def test_arith_a(dut):
    e = Env(dut)
    await e.start()
    for c in CASES_A:
        await e.run_case(*c)


@cocotb.test()
async def test_arith_b(dut):
    e = Env(dut)
    await e.start()
    for c in CASES_B:
        await e.run_case(*c)


@cocotb.test()
async def test_arith_random(dut):
    e = Env(dut)
    await e.start()
    for _ in range(12):
        await e.run_case(*rand_case(e.rng), go_val=e.rng.getrandbits(32))
        if e.rng.random() < 0.5:
            await e.wreg(e.rng.randint(0, 4), e.rng.getrandbits(32))
            await e.rreg(8)
            await e.rreg(9)


@cocotb.test()
async def test_shift_sweep(dut):
    e = Env(dut)
    await e.start()
    await e.wreg(5, 1)
    for s in range(1, 32):
        half = 1 << (s - 1)
        r = s % 3
        bias = half - 1 if r == 0 else half if r == 1 else -half
        await e.wreg(6, s)
        await e.wreg(4, bias)
        await e.go()
        await e.rreg(8)
    await e.wreg(5, 65535)
    for s in (1, 7, 16, 24, 31):
        await e.wreg(6, s | (1 << 8) if s == 16 else s)
        await e.wreg(4, e.rng.randint(-(1 << 31), (1 << 31) - 1) >> (31 - s) if s < 31 else 1 << 30)
        await e.go()
        await e.rreg(8)
        await e.rreg(9)


@cocotb.test()
async def test_go_timing(dut):
    e = Env(dut)
    await e.start()
    await e.run_case(*CASES_A[3], go_val=0)          # first go, then ready
    await e.run_case(*CASES_A[4], go_val=0xFFFFFFFF)  # restart with new operands
    await e.go(0x12345678)                            # restart, same operands
    assert (await e.rreg(10)) == 1
    # results hold while the operands change without a GO
    y = await e.rreg(8)
    acc = await e.rreg(9)
    await e.wreg(0, 0x7F7F7F7F)
    await e.wreg(4, 1000)
    assert (await e.rreg(8)) == y
    assert (await e.rreg(9)) == acc
    # the restart now uses the new operands
    await e.go()
    await e.rreg(8)
    await e.rreg(9)
    # a GO frame with a bad checksum must not start anything
    st, _ = await e.txn(CMD_WRITE, 0x87, 0, bad_chk=True)
    assert st == 1
    assert len(e.led_events) > 0
    assert bit_of(dut.LED0, -1) == 1
    await e.rreg(10)


@cocotb.test()
async def test_reset(dut):
    e = Env(dut)
    await e.start()
    await e.run_case(*CASES_A[0])
    assert bit_of(dut.LED0, -1) == 1
    cov_rst("with_result")
    await RisingEdge(e.clk)
    dut.CPU_RESETN.value = 0
    await ClockCycles(e.clk, 3)
    await Timer(1, "ns")
    assert bit_of(dut.LED0, -1) == 0, "ready not cleared within 3 cycles of reset"
    await ClockCycles(e.clk, 4)
    assert bit_of(dut.LED0, -1) == 0
    dut.CPU_RESETN.value = 1
    await e.after_reset()
    for off in range(11):
        await e.rreg(off)
    assert (await e.rreg(6)) == 1
    # reset with operands loaded but no result
    for off, val in ((0, 0x11223344), (1, 0x55667788), (2, 0x99AABBCC), (3, 0x01020304),
                     (4, 0xFFFF0000), (5, 0x1234), (6, 0x11F)):
        await e.wreg(off, val)
    cov_rst("idle")
    await e.hw_reset(4)
    for off in range(11):
        await e.rreg(off)
    # reset in the middle of a computation: no result may appear afterwards
    await e.run_case(*CASES_A[1])
    mark = len(e.led_events)
    t = cocotb.start_soon(e.send(frame(CMD_WRITE, 0x87, 0)))
    n = 0
    while True:
        await RisingEdge(e.clk)
        n += 1
        # the 8-byte frame alone takes 80 bit times before GO executes
        assert n < 120 * CPB, "LED never fell on GO"
        if len(e.led_events) > mark and e.led_events[mark][1] == 0:
            break
    dut.CPU_RESETN.value = 0
    cov_rst("mid_compute")
    await ClockCycles(e.clk, 4)
    dut.CPU_RESETN.value = 1
    await t
    await e.after_reset()
    assert bit_of(dut.LED0, -1) == 0
    for off in (10, 8, 9, 0, 6):
        await e.rreg(off)
    await e.run_case(*CASES_A[3])  # still works after reset
    assert bit_of(dut.LED0, -1) == 1


@cocotb.test()
async def test_shell_protocol(dut):
    e = Env(dut)
    await e.start()
    assert (await e.txn(CMD_WRITE, 0x03, 0x12345678)) == (0, 0x12345678)
    assert (await e.txn(CMD_READ, 0x03)) == (0, 0x12345678)
    assert (await e.txn(CMD_WRITE, 0x04, 0)) == (0, 0)
    assert (await e.txn(CMD_WRITE, 0x83, 0x1111, bad_chk=True)) == (1, 0)
    st, d = await e.txn(CMD_READ, 0x04)
    assert st == 0 and (d & 0xFF) == 1, f"STATUS {d:#x}"
    assert (await e.txn(3, 0x80, 0)) == (2, 0)
    assert (await e.txn(CMD_READ, 0x20)) == (3, 0)
    assert (await e.txn(CMD_WRITE, 0x05, 1)) == (3, 0)
    assert (await e.txn(CMD_WRITE, 0x00, 5)) == (4, 0)
    assert (await e.txn(CMD_READ, 0x00)) == (0, 0x444F5451)
    await e.rreg(4)  # the bad-checksum write did not land
    # garbage before the sync byte is discarded
    await e.send(bytes([0x00, 0x13, 0xFF]))
    assert (await e.txn(CMD_READ, 0x00)) == (0, 0x444F5451)
    # a frame that stops is dropped after TIMEOUT_CYCLES
    await e.send(bytes([0xA5, 0x01, 0x80, 0x00]))
    await ClockCycles(e.clk, TIMEOUT + 1000)
    assert not e.rx
    assert (await e.txn(CMD_READ, 0x00)) == (0, 0x444F5451)
    await e.rreg(10)


@cocotb.test()
async def test_baud(dut):
    e = Env(dut)
    await e.start()
    st, d = await e.txn(CMD_READ, 0x00)
    assert (st, d) == (0, 0x444F5451)
    t0s = e.last_t0
    assert len(t0s) == 7
    # 0x5A = 01011010 LSB first: start bit and bit 0 are low, so the first low run is 2 bit times
    runs = [r for s, r in e.runs if s == t0s[0]]
    assert runs and runs[0] == 2 * CPB, f"first low run {runs}, expected {2 * CPB}"
    for a, b in zip(t0s, t0s[1:]):
        assert b - a >= 10 * CPB, f"bytes closer than one frame: {b - a}"
    # every low run on the line is a whole number of bit times
    for s, r in e.runs[-20:]:
        assert r % CPB == 0, f"low run of {r} cycles is not a multiple of {CPB}"


@cocotb.test()
async def test_zz_export(dut):
    path = os.environ.get("FDA_COV_OUT")
    if path:
        coverage_db.export_to_yaml(path)
