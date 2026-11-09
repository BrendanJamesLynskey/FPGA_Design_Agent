import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from shell.tests.uart_bfm import UartBfm
from shell.host import protocol as p
import spec_ref as m

CPB = 10
PARAMS = {"CLKS_PER_BIT": CPB, "TIMEOUT_CYCLES": 2000, "BUILD_STAMP": 0}
SEEDS = (1, 2)


class Env:
    def __init__(self, dut):
        self.dut = dut
        self.bfm = UartBfm(dut.CLK100MHZ, dut.UART_TXD_IN, dut.UART_RXD_OUT, CPB)
        self.cache = {}

    async def reset(self):
        d = self.dut
        d.CPU_RESETN.value = 0
        await ClockCycles(d.CLK100MHZ, 20)
        d.CPU_RESETN.value = 1
        await ClockCycles(d.CLK100MHZ, 20)
        self.cache = {}

    async def rd(self, off):
        r = p.decode_response(await self.bfm.transact(p.encode_request(p.CMD_READ, 0x80 + off)))
        assert r.status == p.ST_OK, f"read of window offset {off:#x}: expected OK, got {r.status_name}"
        return r.data

    async def wr(self, off, val):
        r = p.decode_response(await self.bfm.transact(p.encode_request(p.CMD_WRITE, 0x80 + off, val)))
        assert r.status == p.ST_OK, f"write of window offset {off:#x}: expected OK, got {r.status_name}"
        if off != m.GO:
            self.cache[off] = val

    async def load(self, off, val):
        if self.cache.get(off) != val:
            await self.wr(off, val)

    def led0(self):
        # "LED0 shows the ready flag": the port is named LED0 (scalar)
        return int(self.dut.LED0.value) & 1

    async def run(self, a, w, bias, mult, shift, relu):
        await self.load(m.A_LO, m.pack4(a[:4]))
        await self.load(m.A_HI, m.pack4(a[4:]))
        await self.load(m.W_LO, m.pack4(w[:4]))
        await self.load(m.W_HI, m.pack4(w[4:]))
        await self.load(m.BIAS, bias & m.MASK32)
        await self.load(m.MULT, mult)
        await self.load(m.CTRL, m.ctrl_word(shift, relu))
        await self.wr(m.GO, 1)
        # Q3: READY within 8 clocks of go; the go transaction takes far longer than that.
        assert self.led0() == 1, "after go: expected ready flag (LED0) = 1, design showed 0"
        y = await self.rd(m.Y)
        acc = await self.rd(m.ACC)
        ey, eacc = m.expected(a, w, bias, mult, shift, relu)
        args = f"a={a} w={w} bias={bias} mult={mult} shift={shift} relu={relu}"
        assert m.s32(acc) == eacc, f"ACC expected {eacc}, design read {m.s32(acc)} for {args}"
        # width of Y readback (sign/zero extension) is not specified: compare low 8 bits as signed
        assert m.s8(y) == ey, f"y expected {ey} (signed 8-bit), design read {m.s8(y)} (raw {y:#x}) for {args}"


async def start(dut):
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, units="ns").start())
    env = Env(dut)
    dut.CPU_RESETN.value = 1
    await env.reset()
    return env


@cocotb.test()
async def design_id_reads_DOTQ(dut):
    env = await start(dut)
    r = p.decode_response(await env.bfm.transact(p.encode_request(p.CMD_READ, p.REG_DESIGN_ID)))
    assert r.data == m.DESIGN_ID, f"DESIGN_ID expected 'DOTQ' = {m.DESIGN_ID:#010x}, read {r.data:#010x}"


@cocotb.test()
async def ctrl_reset_value_and_masking(dut):
    env = await start(dut)
    v = await env.rd(m.CTRL)
    assert v == 1, f"CTRL reset value expected 1, read {v:#x}"
    await env.wr(m.CTRL, 0xFFFFFFFF)
    v = await env.rd(m.CTRL)
    assert v == 0x11F, f"CTRL stores only [4:0] and [8]: expected 0x11F after writing all ones, read {v:#x}"
    await env.wr(m.MULT, 0xFFFFFFFF)
    v = await env.rd(m.MULT)
    assert v >> 16 == 0, f"MULT [31:16] expected to read 0, read {v:#010x}"


@cocotb.test()
async def directed_extremes_halves_and_limits(dut):
    env = await start(dut)
    Z = [0] * 8
    cases = [
        # extreme operands: most negative products and most positive products
        ([-128] * 8, [127] * 8, 0, 65535, 31, 0),
        ([-128] * 8, [127] * 8, 0, 65535, 31, 1),
        ([-128] * 8, [-127] * 8, 0, 3, 12, 0),
        ([127] * 8, [-127] * 8, 7, 1, 1, 0),
        ([127] * 8, [127] * 8, 0, 65535, 20, 1),
        ([-128] * 8, [-127] * 8, 2**30, 65535, 31, 0),
        # exact halves going up: 2.5 -> 3, -2.5 -> -2
        (Z, Z, 5, 1, 1, 0),
        (Z, Z, -5, 1, 1, 0),
        (Z, Z, -3, 1, 1, 0),
        (Z, Z, 2, 1, 2, 0),
        (Z, Z, -2, 1, 2, 0),
        (Z, Z, 3, 1, 2, 0),
        # limit boundaries
        (Z, Z, 254, 1, 1, 0),
        (Z, Z, 255, 1, 1, 0),
        (Z, Z, -256, 1, 1, 0),
        (Z, Z, -257, 1, 1, 0),
        (Z, Z, 1000, 1, 1, 0),
        (Z, Z, -1000, 1, 1, 1),
        (Z, Z, -1, 1, 1, 1),
        (Z, Z, 1, 1, 1, 1),
        # mixed signs
        ([1, -2, 3, -4, 5, -6, 7, -8], [-9, 10, -11, 12, -13, 14, -15, 16], 100, 1000, 10, 0),
    ]
    for c in cases:
        await env.run(*c)


@cocotb.test()
async def random_vectors(dut):
    env = await start(dut)
    rng = random.Random(1234)
    for _ in range(10):
        a = [rng.randint(-128, 127) for _ in range(8)]
        w = [rng.randint(-127, 127) for _ in range(8)]
        bias = rng.randint(-2**20, 2**20)
        mult = rng.randint(0, 65535)
        shift = rng.randint(8, 24)
        await env.run(a, w, bias, mult, shift, rng.randint(0, 1))


@cocotb.test()
async def reset_clears_ready_and_loaded_numbers(dut):
    env = await start(dut)
    await env.run([5] * 8, [3] * 8, 10, 1000, 4, 0)
    assert env.led0() == 1, "LED0 expected to show ready = 1 after a result"
    await env.reset()
    assert env.led0() == 0, "after CPU_RESETN: expected ready flag (LED0) = 0"
    y = await env.rd(m.Y)
    acc = await env.rd(m.ACC)
    assert y == 0 and acc == 0, f"Y and ACC expected to read 0 while not ready, read {y:#x}, {acc:#x}"
    v = await env.rd(m.CTRL)
    assert v == 1, f"CTRL expected reset value 1 after CPU_RESETN, read {v:#x}"
    v = await env.rd(m.MULT)
    assert v == 0, f"MULT expected cleared by CPU_RESETN, read {v:#x}"
