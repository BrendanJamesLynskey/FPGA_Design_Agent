import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

import spec_ref as R
from shell.tests.uart_bfm import UartBfm
from shell.host import protocol as p

CPB = 8
PARAMS = {"CLKS_PER_BIT": CPB, "TIMEOUT_CYCLES": 1500, "BUILD_STAMP": 0}
SEEDS = (1,)


class Env:
    def __init__(self, dut):
        self.dut = dut
        self.cache = {}
        self.bfm = UartBfm(dut.CLK100MHZ, dut.UART_TXD_IN, dut.UART_RXD_OUT, CPB)

    async def reset(self):
        self.dut.CPU_RESETN.value = 0
        self.dut.UART_TXD_IN.value = 1
        await ClockCycles(self.dut.CLK100MHZ, 20)
        self.dut.CPU_RESETN.value = 1
        await ClockCycles(self.dut.CLK100MHZ, 20)
        self.cache = {}

    async def xact(self, cmd, addr, data=0):
        raw = await self.bfm.transact(p.encode_request(cmd, addr, data))
        await ClockCycles(self.dut.CLK100MHZ, 2 * CPB)
        return p.decode_response(raw)

    async def wr(self, off, val, force=False):
        if not force and self.cache.get(off) == val:
            return
        r = await self.xact(p.CMD_WRITE, R.WINDOW_BASE + off, val)
        assert r.status == p.ST_OK, f"write offset {off:#x}: expected OK, got {r.status_name}"
        self.cache[off] = val

    async def rd(self, off):
        r = await self.xact(p.CMD_READ, R.WINDOW_BASE + off)
        assert r.status == p.ST_OK, f"read offset {off:#x}: expected OK, got {r.status_name}"
        return r.data

    def led0(self):
        return str(self.dut.LED.value)[-1] == "1"

    async def load(self, a, w, bias, mult, shift, relu):
        await self.wr(R.A_LO, R.pack_i8(a[:4]))
        await self.wr(R.A_HI, R.pack_i8(a[4:]))
        await self.wr(R.W_LO, R.pack_i8(w[:4]))
        await self.wr(R.W_HI, R.pack_i8(w[4:]))
        await self.wr(R.BIAS, bias & 0xFFFFFFFF)
        await self.wr(R.MULT, mult)
        await self.wr(R.CTRL, R.ctrl_word(shift, relu))

    async def run(self, a, w, bias, mult, shift, relu):
        await self.load(a, w, bias, mult, shift, relu)
        await self.wr(R.GO, 1, force=True)
        assert self.led0(), "ready flag (LED0) should be 1 after the result is done"
        y = R.s8(await self.rd(R.Y) & 0xFF)
        acc = R.s32(await self.rd(R.ACC))
        return y, acc

    async def check(self, a, w, bias, mult, shift, relu):
        ey, eacc = R.expected(a, w, bias, mult, shift, relu)
        y, acc = await self.run(a, w, bias, mult, shift, relu)
        ctx = f"a={a} w={w} bias={bias} mult={mult} shift={shift} relu={relu}"
        assert acc == eacc, f"acc expected {eacc} (sum of 8 products + bias), design gave {acc}; {ctx}"
        assert y == ey, f"y expected {ey} (acc*mult/2^shift rounded half up, limited), design gave {y}; {ctx}"


async def setup(dut):
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, unit="ns").start())
    env = Env(dut)
    await env.reset()
    return env


Z8 = [0] * 8


@cocotb.test()
async def design_id_is_dotq(dut):
    env = await setup(dut)
    r = await env.xact(p.CMD_READ, p.REG_DESIGN_ID)
    assert r.data == R.DESIGN_ID, f'DESIGN_ID expected "DOTQ" 0x444F5451, got {r.data:#010x}'


@cocotb.test()
async def reset_values_and_register_readback(dut):
    env = await setup(dut)
    assert not env.led0(), "after reset the ready flag (LED0) should be 0"
    assert await env.rd(R.CTRL) & 0x1FF == 1, "CTRL reset value should be 1 (shift=1, relu=0)"
    for off in (R.A_LO, R.A_HI, R.W_LO, R.W_HI, R.BIAS, R.MULT):
        assert await env.rd(off) == 0, f"register {off:#x} should reset to 0"
    pats = {R.A_LO: 0x80FF017F, R.A_HI: 0x12345678, R.W_LO: 0x7F81FE02,
            R.W_HI: 0xA5C3F00F, R.BIAS: 0x87654321}
    for off, v in pats.items():
        await env.wr(off, v, force=True)
        got = await env.rd(off)
        assert got == v, f"register {off:#x} wrote {v:#010x}, read back {got:#010x}"
    await env.wr(R.MULT, 0xFFFF, force=True)
    assert await env.rd(R.MULT) & 0xFFFF == 0xFFFF, "MULT should hold a 16-bit value"
    for v in (0x11F, 0x005, 0x01F):
        await env.wr(R.CTRL, v, force=True)
        got = await env.rd(R.CTRL) & 0x11F
        assert got == v, f"CTRL wrote {v:#x} (shift [4:0], relu [8]), read {got:#x}"
    for addr in (0x8B, 0xA0, 0xFF):
        r = await env.xact(p.CMD_READ, addr)
        assert r.status == p.ST_OK and r.data == 0, f"unmapped {addr:#x} should read 0, got {r.data:#x}"


@cocotb.test()
async def dot_product_lanes_and_signs(dut):
    env = await setup(dut)
    await env.check([1] * 8, [1] * 8, 0, 1, 1, 0)  # acc 8, y 4
    await env.check([1, -2, 3, -4, 5, -6, 7, -8], [9, 8, -7, 6, -5, 4, 3, -2], 0, 1, 1, 0)
    await env.check([1, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 5], 0, 1, 1, 0)  # no cross-lane pairing
    await env.check([0, 0, 0, 0, 0, 0, 0, 3], [0, 0, 0, 0, 0, 0, 0, 7], 0, 1, 1, 0)
    await env.check([0, 0, 0, 2, 0, 0, 0, 0], [0, 0, 0, 11, 0, 0, 0, 0], 1000, 1, 1, 0)
    await env.check([-128] * 8, [-127] * 8, 0, 1, 1, 0)  # acc 130048
    await env.check([127] * 8, [-127] * 8, 0, 1, 1, 0)
    await env.check([-128] * 8, [127] * 8, 0, 1, 1, 0)
    await env.check([-128] * 8, [-127] * 8, 0, 65535, 31, 0)
    await env.check([-128] * 8, [-127] * 8, -2000000000, 65535, 20, 0)
    await env.check([127] * 8, [127] * 8, 2000000000, 65535, 31, 0)
    await env.check([-128] * 8, [127] * 8, -2000000000, 65535, 31, 0)


@cocotb.test()
async def rounding_exact_halves_go_up(dut):
    env = await setup(dut)
    cases = [(5, 1, 1), (-5, 1, 1), (3, 1, 2), (1, 1, 2), (2, 1, 2), (-2, 1, 2), (-1, 1, 2),
             (-3, 1, 2), (6, 1, 2), (-6, 1, 2), (1, 1, 31), (1 << 30, 1, 31), (-(1 << 30), 1, 31),
             (1, 65535, 16), (-1, 65535, 16), (7, 2, 2), (-7, 2, 2), (100, 3, 3), (-100, 3, 3),
             (9, 1, 4), (-9, 1, 4)]
    for bias, mult, shift in cases:
        await env.check(Z8, Z8, bias, mult, shift, 0)
    # same halves also from products, not only from bias
    await env.check([1, 1, 1, 1, 1, 0, 0, 0], [1] * 8, 0, 1, 1, 0)  # 5 -> 2.5 -> 3
    await env.check([-1, -1, -1, -1, -1, 0, 0, 0], [1] * 8, 0, 1, 1, 0)  # -5 -> -2


@cocotb.test()
async def limiting_at_both_ends(dut):
    env = await setup(dut)
    for acc in (254, 255, 256, 257, 1000, -254, -255, -256, -257, -258, -259, -1000, 253, -253):
        await env.check(Z8, Z8, acc, 1, 1, 0)
    for acc in (127, 128, -128, -129, 126, -127):
        await env.check(Z8, Z8, acc, 1, 1 if False else 1, 0)
        await env.check(Z8, Z8, acc * 2, 1, 1, 0)
    await env.check(Z8, Z8, 5000, 0, 5, 0)  # mult 0 -> 0


@cocotb.test()
async def relu_limits_to_0_127(dut):
    env = await setup(dut)
    for acc in (-1000, -258, -5, -2, -1, 0, 1, 5, 253, 254, 256, 1000):
        await env.check(Z8, Z8, acc, 1, 1, 1)
        await env.check(Z8, Z8, acc, 1, 1, 0)
    await env.check([-128] * 8, [127] * 8, 0, 65535, 31, 1)
    await env.check([-128] * 8, [-127] * 8, 0, 65535, 31, 1)
    # relu bit 8 only; shift 31 with relu
    await env.check(Z8, Z8, -(1 << 30), 1, 31, 1)
    await env.check(Z8, Z8, (1 << 30) + 12345, 1, 31, 1)


@cocotb.test()
async def random_vectors_match_model(dut):
    env = await setup(dut)
    rng = random.Random(20240601 + 7)
    for _ in range(18):
        a = [rng.randint(-128, 127) for _ in range(8)]
        w = [rng.randint(-127, 127) for _ in range(8)]
        bias = rng.choice([0, rng.randint(-5000, 5000), rng.randint(-10**9, 10**9)])
        mult = rng.choice([rng.randint(0, 65535), rng.randint(1, 300)])
        acc = R.dot(a, w, bias)
        tgt = (abs(acc) * mult).bit_length() - 7 + rng.randint(-1, 1)
        shift = max(1, min(31, tgt)) if rng.random() < 0.8 else rng.randint(1, 31)
        await env.check(a, w, bias, mult, shift, rng.randint(0, 1))


@cocotb.test()
async def ready_clears_on_go_and_returns_within_8_clocks(dut):
    env = await setup(dut)
    await env.run([3] * 8, [4] * 8, 0, 1, 1, 0)
    assert env.led0(), "ready (LED0) should be 1 after a completed result"
    await env.load([5] * 8, [6] * 8, 7, 3, 2, 0)
    samples = []
    stop = [False]

    async def mon():
        while not stop[0]:
            await RisingEdge(dut.CLK100MHZ)
            samples.append(env.led0())

    cocotb.start_soon(mon())
    await env.wr(R.GO, 1, force=True)
    stop[0] = True
    await RisingEdge(dut.CLK100MHZ)
    assert False in samples, "READY should clear on GO (LED0 never went low)"
    i = samples.index(False)
    j = i
    while j < len(samples) and not samples[j]:
        j += 1
    assert j < len(samples), "READY did not become 1 again after GO"
    assert j - i <= 9, f"READY should become 1 within 8 clocks of GO; low for {j - i} clocks"
    assert all(samples[j:]), "READY should stay 1 until the next GO"
    assert env.led0(), "LED0 should show ready=1"
    ey, eacc = R.expected([5] * 8, [6] * 8, 7, 3, 2, 0)
    assert R.s32(await env.rd(R.ACC)) == eacc, f"acc expected {eacc}"
    assert R.s8(await env.rd(R.Y)) == ey, f"y expected {ey}"
    assert env.led0(), "READY should stay 1 while reading results"


@cocotb.test()
async def reset_clears_loaded_numbers_and_ready(dut):
    env = await setup(dut)
    await env.run([9] * 8, [-9] * 8, 77, 5, 3, 1)
    assert env.led0(), "ready should be set before reset"
    await env.reset()
    assert not env.led0(), "CPU_RESETN should clear the ready flag (LED0)"
    for off in (R.A_LO, R.A_HI, R.W_LO, R.W_HI, R.BIAS, R.MULT):
        assert await env.rd(off) == 0, f"CPU_RESETN should clear loaded register {off:#x}"
    assert await env.rd(R.CTRL) & 0x1FF == 1, "CTRL should be back at reset value 1"
    await env.check([100, -100, 50, -50, 1, 2, 3, 4], [5, 6, -7, 8, 9, -10, 11, 12], 33, 77, 5, 0)
