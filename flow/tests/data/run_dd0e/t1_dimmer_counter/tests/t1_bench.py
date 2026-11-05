"""cocotb bench for t1_top: RTL checked against the blind model (model.py).

Small timing parameters (same values go to the model):
  DEBOUNCE 20, PWM period 256, scan 16 cycles/digit, baud 20 cycles/bit.
Output pins are compared with the model within a small latency window
(the RTL may register outputs / synchronise reset a few cycles differently);
register values read over the UART shell are compared exactly.
"""
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import RisingEdge, ReadOnly, Timer  # noqa: E402
from cocotb_coverage.coverage import CoverPoint, coverage_db  # noqa: E402

P = dict(DEBOUNCE_CYCLES=20, PWM_PERIOD_CYCLES=256, SCAN_DIGIT_CYCLES=16,
         BAUD_DIV_CYCLES=20)
DEB = P["DEBOUNCE_CYCLES"]
PWM = P["PWM_PERIOD_CYCLES"]
SCAN = P["SCAN_DIGIT_CYCLES"]
BD = P["BAUD_DIV_CYCLES"]
HIST = 6

EVENTS = ["up", "down", "centre", "wrap_up", "wrap_down", "bounce", "glitch",
          "hold", "simul_cu", "simul_ud", "sw_mode", "disp_off", "uart_read",
          "uart_write", "reset_mid", "unknown_addr", "pwm_duty"]


@CoverPoint("top.event", xf=lambda e: e, bins=EVENTS)
def cov(e):
    pass


def xor8(bs):
    r = 0
    for b in bs:
        r ^= b
    return r


def val(sig):
    try:
        return int(sig.value)
    except ValueError:
        return None


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.m = model.Model(**P)
        self.inp = {"BTNU": 0, "BTND": 0, "BTNC": 0, "SW": 0, "UART_RXD": 1}
        self.hist = []
        self.check = False
        self.settle = 0
        self.last = {}

    async def start(self):
        d = self.dut
        d.CPU_RESETN.value = 0
        self.set(BTNU=0, BTND=0, BTNC=0, SW=0, UART_RXD=1)
        cocotb.start_soon(Clock(d.CLK100MHZ, 10, "ns").start())
        await Timer(1, "ns")
        await self.reset()

    def set(self, **kw):
        for k, v in kw.items():
            self.inp[k] = v
            getattr(self.dut, k).value = v

    async def tick(self):
        d = self.dut
        await RisingEdge(d.CLK100MHZ)
        await ReadOnly()
        out = (val(d.LED), val(d.SEG), val(d.DP), val(d.AN))
        txd = val(d.UART_TXD)
        mo = self.m.step(dict(self.inp))
        mt = (mo["LED"], mo["SEG"], mo["DP"], mo["AN"])
        self.hist.append(mt)
        self.hist = self.hist[-HIST:]
        self.last = {"LED": out[0], "SEG": out[1], "DP": out[2], "AN": out[3]}
        if self.check and self.settle == 0:
            assert out in self.hist, (
                "output mismatch dut(LED,SEG,DP,AN)=%s model window=%s" % (out, self.hist))
        if self.settle > 0:
            self.settle -= 1
        await Timer(1, "ns")
        return txd

    async def ticks(self, n):
        for _ in range(n):
            await self.tick()

    async def reset(self, n=4):
        self.check = False
        self.dut.CPU_RESETN.value = 0
        await self.ticks(n)
        self.dut.CPU_RESETN.value = 1
        self.m.reset()
        self.hist = []
        self.settle = 12
        self.check = True
        await self.ticks(1)

    # ---------------- UART shell -----------------
    async def uart(self, cmd, addr, data=0):
        body = bytes([cmd, addr]) + data.to_bytes(4, "little")
        req = bytes([0xA5]) + body + bytes([xor8(body)])
        bits = []
        for b in req:
            for bit in [0] + [(b >> i) & 1 for i in range(8)] + [1]:
                bits += [bit] * BD
        prev = self.check
        self.check = False
        rx = []
        st = {"n": None, "cur": 0}

        def feed(txd):
            if st["n"] is None:
                if txd == 0:
                    st["n"] = 0
                    st["cur"] = 0
                return
            st["n"] += 1
            n = st["n"]
            if n >= BD // 2 and (n - BD // 2) % BD == 0:
                k = (n - BD // 2) // BD
                if 1 <= k <= 8:
                    st["cur"] |= (txd & 1) << (k - 1)
                elif k == 9:
                    rx.append(st["cur"])
                    st["n"] = None

        for bit in bits:
            self.set(UART_RXD=bit)
            feed(await self.tick())
        self.set(UART_RXD=1)
        lim = 0
        while len(rx) < 7 and lim < 40 * 10 * BD:
            feed(await self.tick())
            lim += 1
        assert len(rx) == 7, "UART response incomplete: %s" % rx
        await self.ticks(2 * BD)
        self.check = prev
        self.settle = max(self.settle, 2 * PWM + 8)
        assert rx[0] == 0x5A, rx
        assert xor8(rx[1:6]) == rx[6], rx
        return rx[1], int.from_bytes(bytes(rx[2:6]), "little")

    async def rd(self, off):
        st, data = await self.uart(1, 0x80 + off)
        cov("uart_read")
        assert st == 0, "read status %d off %d" % (st, off)
        exp = self.m.read_reg(off)
        assert data == exp, "reg %d: dut 0x%X model 0x%X" % (off, data, exp)
        return data

    async def wr(self, off, v):
        st, data = await self.uart(2, 0x80 + off, v)
        cov("uart_write")
        assert st == 0, "write status %d off %d" % (st, off)
        self.m.write_reg(off, v)

    # ---------------- buttons -----------------
    async def press(self, names, bounce=0, hold=None, rel=True):
        if isinstance(names, str):
            names = [names]
        hold = DEB + 20 if hold is None else hold
        for n in names:
            cov({"BTNU": "up", "BTND": "down", "BTNC": "centre"}[n])
        if bounce:
            cov("bounce")
        for _ in range(bounce):
            self.set(**{n: 1 for n in names})
            await self.ticks(random.randint(1, 6))
            self.set(**{n: 0 for n in names})
            await self.ticks(random.randint(1, 6))
        self.set(**{n: 1 for n in names})
        await self.ticks(hold)
        if not rel:
            return
        for _ in range(bounce):
            self.set(**{n: 0 for n in names})
            await self.ticks(random.randint(1, 6))
            self.set(**{n: 1 for n in names})
            await self.ticks(random.randint(1, 6))
        self.set(**{n: 0 for n in names})
        await self.ticks(DEB + 20)


async def setup(dut):
    random.seed(cocotb.RANDOM_SEED)
    b = Bench(dut)
    await b.start()
    return b


async def check_all_regs(b):
    for off in (0, 4, 8, 12, 16, 20, 24, 28, 32):
        await b.rd(off)


# =====================================================================
@cocotb.test()
async def test_reset_and_id(dut):
    b = await setup(dut)
    assert await b.rd(0) == 0x54314443
    await check_all_regs(b)
    assert b.m.read_reg(4) == 0 and b.m.read_reg(8) == 0x80 and b.m.read_reg(12) == 0
    st, data = await b.uart(1, 0x00)
    assert st == 0 and data == 0x54314443
    await b.ticks(600)


@cocotb.test()
async def test_buttons_basic(dut):
    b = await setup(dut)
    await b.wr(8, 0xFF)
    await b.press("BTNU")
    assert await b.rd(4) == 1
    await b.press("BTNU")
    assert await b.rd(4) == 2
    await b.press("BTND")
    assert await b.rd(4) == 1
    await b.press("BTND")
    assert await b.rd(4) == 0
    await b.press("BTND")
    assert await b.rd(4) == 0xFFFF
    cov("wrap_down")
    await b.press("BTNU")
    assert await b.rd(4) == 0
    cov("wrap_up")
    await b.press("BTNU")
    await b.press("BTNU")
    await b.press("BTNC")
    assert await b.rd(4) == 0
    await b.press("BTNC")
    assert await b.rd(4) == 0
    for off in (24, 28, 32):
        await b.rd(off)
    assert b.m.read_reg(24) == 5 and b.m.read_reg(28) == 3 and b.m.read_reg(32) == 2


@cocotb.test()
async def test_wrap_write(dut):
    b = await setup(dut)
    await b.wr(4, 0xFFFF)
    assert await b.rd(4) == 0xFFFF
    await b.press("BTNU")
    assert await b.rd(4) == 0
    cov("wrap_up")
    await b.press("BTND")
    assert await b.rd(4) == 0xFFFF
    cov("wrap_down")
    await b.wr(4, 0x12345)
    assert await b.rd(4) == 0x2345
    await b.wr(4, 0x7FFF)
    await b.press("BTNU")
    assert await b.rd(4) == 0x8000
    await b.press("BTND")
    assert await b.rd(4) == 0x7FFF
    await b.press("BTNC")
    assert await b.rd(4) == 0


@cocotb.test()
async def test_bounce_and_hold(dut):
    b = await setup(dut)
    await b.wr(8, 0xFF)
    # bounce yields exactly one count
    await b.press("BTNU", bounce=4)
    assert await b.rd(4) == 1
    await b.press("BTND", bounce=3)
    await b.press("BTND", bounce=5)
    assert await b.rd(4) == 0xFFFF
    # short glitch: no count
    cov("glitch")
    for _ in range(3):
        await b.press("BTNU", hold=DEB // 2 - 2)
    await b.press("BTNC", hold=5)
    assert await b.rd(4) == 0xFFFF
    # long hold: one count only
    cov("hold")
    await b.press("BTNU", hold=6 * DEB)
    assert await b.rd(4) == 0
    # held button visible in BUTTONS
    await b.press(["BTNU", "BTNC"], hold=DEB + 30, rel=False)
    assert await b.rd(16) == 5
    b.set(BTNU=0, BTNC=0)
    await b.ticks(DEB + 30)
    assert await b.rd(16) == 0
    for off in (24, 28, 32):
        await b.rd(off)


@cocotb.test()
async def test_priority(dut):
    b = await setup(dut)
    await b.wr(4, 5)
    cov("simul_cu")
    await b.press(["BTNC", "BTNU"])
    assert await b.rd(4) == 0
    cov("simul_ud")
    await b.press(["BTNU", "BTND"])
    assert await b.rd(4) == 1
    await b.press(["BTNU", "BTND", "BTNC"])
    assert await b.rd(4) == 0
    await b.press(["BTND", "BTNC"])
    assert await b.rd(4) == 0
    for off in (24, 28, 32):
        await b.rd(off)
    assert b.m.read_reg(24) == 3 and b.m.read_reg(28) == 3 and b.m.read_reg(32) == 3


@cocotb.test()
async def test_pwm_and_brightness(dut):
    b = await setup(dut)
    await b.wr(4, 0xFFFF)
    for br in (0, 1, 0x40, 0x80, 0xC3, 0xFF):
        await b.wr(8, br)
        await b.ticks(300)
        n = 0
        for _ in range(2 * PWM):
            await b.tick()
            led = b.last["LED"]
            assert led in (0, 0xFFFF), led
            n += led != 0
        assert n == 2 * br, "duty br=%d on=%d" % (br, n)
        cov("pwm_duty")
    # SW mode
    await b.wr(8, 0x20)
    await b.wr(12, 1)
    cov("sw_mode")
    b.set(SW=0xAB37)
    await b.ticks(300)
    n = 0
    for _ in range(2 * PWM):
        await b.tick()
        n += b.last["LED"] != 0
    assert n == 2 * 0x37, n
    assert await b.rd(8) == 0x20
    assert await b.rd(20) == 0xAB37
    assert await b.rd(12) == 1
    # duty changes only at a period boundary
    for lo, hi in ((0x30, 0x90), (0x90, 0x30), (0x30, 0x77)):
        b.set(SW=lo)
        await b.ticks(2 * PWM)
        trace = []
        for i in range(6 * PWM):
            if i == 3 * PWM + 37:
                b.set(SW=hi)
            await b.tick()
            trace.append(b.last["LED"] != 0)
        runs = []
        c = 0
        for i, v in enumerate(trace):
            if v:
                c += 1
            elif c:
                runs.append((i - c, c))
                c = 0
        runs = runs[1:] if trace[0] else runs
        for _, ln in runs:
            assert ln in (lo, hi), "glitched PWM run %d (lo %d hi %d)" % (ln, lo, hi)
        assert any(ln == lo for _, ln in runs) and any(ln == hi for _, ln in runs)
    # back to register mode
    await b.wr(12, 0)
    await b.wr(8, 0x55)
    await b.ticks(2 * PWM)
    n = 0
    for _ in range(2 * PWM):
        await b.tick()
        n += b.last["LED"] != 0
    assert n == 2 * 0x55
    # LED shows the counter bits
    await b.wr(4, 0xA5C3)
    await b.wr(8, 0xFF)
    await b.ticks(300)
    seen = set()
    for _ in range(PWM):
        await b.tick()
        seen.add(b.last["LED"])
    assert seen == {0, 0xA5C3}, seen
    # bright reg masks to 8 bits, ctrl to 2 bits
    await b.wr(8, 0x1FF)
    assert await b.rd(8) == 0xFF
    await b.wr(12, 0xFF)
    assert await b.rd(12) == 3
    await b.wr(12, 0)


@cocotb.test()
async def test_display(dut):
    b = await setup(dut)
    await b.wr(4, 0x1234)
    await b.wr(8, 0xA5)
    await b.ticks(300)
    N = 16 * SCAN
    cnt = {}
    segs = {}
    anydp = set()
    for _ in range(N):
        await b.tick()
        an = b.last["AN"]
        anydp.add(b.last["DP"])
        low = [i for i in range(8) if not (an >> i) & 1]
        assert len(low) <= 1, an
        d = low[0] if low else -1
        cnt[d] = cnt.get(d, 0) + 1
        segs.setdefault(d, set()).add(b.last["SEG"])
    assert anydp == {1}
    for d in (0, 1, 2, 3, 6, 7):
        assert cnt.get(d, 0) == 2 * SCAN, (d, cnt)
        assert len(segs[d]) == 1
    assert cnt.get(4, 0) == 0 and cnt.get(5, 0) == 0
    assert cnt.get(-1, 0) == 4 * SCAN, cnt
    assert len({next(iter(segs[d])) for d in (0, 1, 2, 3)}) == 4
    assert next(iter(segs[6])) != next(iter(segs[7]))
    # SW mode brightness shown
    await b.wr(12, 1)
    b.set(SW=0x3C)
    await b.ticks(2 * PWM + 50)
    await b.ticks(8 * SCAN)
    # display off
    await b.wr(12, 3)
    cov("disp_off")
    await b.ticks(10)
    for _ in range(N):
        await b.tick()
        assert b.last["AN"] == 0xFF
        assert b.last["DP"] == 1
    await b.wr(12, 0)
    await b.ticks(2 * N)
    # other values
    for c, br in ((0x0000, 0x00), (0xFFFF, 0xFF), (0x89AB, 0x7E), (0xCDEF, 0x01)):
        await b.wr(4, c)
        await b.wr(8, br)
        await b.ticks(2 * PWM + 4 * N)


@cocotb.test()
async def test_uart_misc(dut):
    b = await setup(dut)
    # unknown addresses read 0
    cov("unknown_addr")
    for off in (36, 40, 0x7C, 0x7F):
        st, data = await b.uart(1, 0x80 + off)
        assert st == 0 and data == 0, (off, st, data)
    # writes to ro / unknown ignored
    for off in (0, 16, 20, 24, 28, 32, 36):
        await b.wr(off, 0xFFFFFFFF)
    await check_all_regs(b)
    # counter stays within 16 bits, upper bits read 0
    await b.wr(4, 0xFFFFFFFF)
    assert await b.rd(4) == 0xFFFF
    await b.wr(4, 0)
    # shell scratch
    st, data = await b.uart(2, 0x03, 0x12345678)
    assert st == 0
    st, data = await b.uart(1, 0x03)
    assert st == 0 and data == 0x12345678
    # ro write to ID
    st, data = await b.uart(2, 0x00, 0)
    assert st == 4
    await check_all_regs(b)


@cocotb.test()
async def test_reset_mid_operation(dut):
    b = await setup(dut)
    await b.press("BTNU")
    await b.press("BTNU")
    await b.press("BTND")
    await b.press("BTNC")
    await b.wr(4, 0x4321)
    await b.wr(8, 0x11)
    await b.wr(12, 3)
    b.set(SW=0x00F0)
    await b.ticks(10)
    await check_all_regs(b)
    cov("reset_mid")
    await b.reset()
    await b.ticks(600)
    await check_all_regs(b)
    for off, v in ((4, 0), (8, 0x80), (12, 0), (24, 0), (28, 0), (32, 0), (16, 0)):
        assert b.m.read_reg(off) == v
    # reset while a button is mid-debounce
    b.set(BTNU=1)
    await b.ticks(DEB // 2)
    b.check = False
    dut.CPU_RESETN.value = 0
    await b.ticks(3)
    b.set(BTNU=0)
    await b.reset()
    await b.ticks(DEB + 30)
    assert await b.rd(4) == 0
    assert await b.rd(24) == 0


@cocotb.test()
async def test_random(dut):
    b = await setup(dut)
    rnd = random.Random(cocotb.RANDOM_SEED)
    names = ["BTNU", "BTND", "BTNC"]

    def cls():
        return rnd.choice([0, 1, 0xFFFF, 0xFFFE, 0x7FFF, rnd.getrandbits(16)])

    for _ in range(40):
        r = rnd.random()
        if r < 0.40:
            await b.press(rnd.choice(names), bounce=rnd.randint(0, 3),
                          hold=rnd.choice([None, DEB + 5, 2 * DEB]))
        elif r < 0.50:
            await b.press(rnd.sample(names, 2), bounce=rnd.randint(0, 2))
        elif r < 0.60:
            await b.wr(4, cls())
        elif r < 0.68:
            await b.wr(8, rnd.choice([0, 1, 0x80, 0xFF, rnd.getrandbits(8)]))
        elif r < 0.73:
            await b.wr(12, rnd.getrandbits(2))
        elif r < 0.85:
            b.set(SW=rnd.getrandbits(16))
            await b.ticks(rnd.randint(5, 600))
        else:
            await b.rd(rnd.choice([0, 4, 8, 12, 16, 20, 24, 28, 32]))
    await check_all_regs(b)


@cocotb.test()
async def test_zz_export(dut):
    # runs last: export functional coverage
    path = os.environ.get("FDA_COV_OUT")
    if path:
        coverage_db.export_to_yaml(path)
