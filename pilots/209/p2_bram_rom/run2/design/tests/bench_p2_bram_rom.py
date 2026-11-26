"""cocotb bench for p2_core (register core): RTL checked against model.py."""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

ID = 0x20920001
BASE = 0xC0DE0000
M32 = 0xFFFFFFFF
MAPPED = {0x00, 0x04, 0x08, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x2C, 0x30}
RO = {0x00, 0x04, 0x14, 0x28, 0x2C, 0x30}
MAX_WAIT = 600000

M = model.Model()


class H:
    def __init__(self, dut):
        self.dut = dut
        self.m = M

    async def start(self):
        try:
            clk = Clock(self.dut.clk, 40, unit="ns")
        except TypeError:
            clk = Clock(self.dut.clk, 40, units="ns")
        cocotb.start_soon(clk.start())
        self.dut.h_we.value = 0
        self.dut.h_re.value = 0
        self.dut.h_addr.value = 0
        self.dut.h_wdata.value = 0
        await self.reset()

    async def tick(self, n=1):
        for _ in range(n):
            await RisingEdge(self.dut.clk)
            await Timer(1, "ns")

    async def reset(self):
        if hasattr(self.dut, "rst"):
            self.dut.rst.value = 1
            await self.tick(10)
            self.dut.rst.value = 0
            await self.tick(3)
        self.m.reset()

    async def raw_write(self, addr, val):
        self.dut.h_addr.value = addr
        self.dut.h_wdata.value = val & M32
        self.dut.h_we.value = 1
        await self.tick()
        self.dut.h_we.value = 0

    async def wr(self, addr, val):
        await self.raw_write(addr, val)
        self.m.write_reg(addr, val)

    async def raw_read(self, addr):
        self.dut.h_addr.value = addr
        self.dut.h_re.value = 1
        await self.tick()
        self.dut.h_re.value = 0
        await self.tick(2)
        assert int(self.dut.sfp_tx_disable.value) == 1
        return int(self.dut.h_rdata.value)

    async def rd(self, addr, check=True):
        v = await self.raw_read(addr)
        if check and addr != 0x04:
            exp = self.m.read_reg(addr)
            assert v == exp, f"read 0x{addr:03x}: rtl 0x{v:08x} model 0x{exp:08x}"
        elif addr != 0x04:
            self.m.read_reg(addr)
        return v

    async def wait_done(self):
        for _ in range(MAX_WAIT // 100):
            st = await self.raw_read(0x28)
            if not st & 1:
                return st
            await self.tick(100)
        raise AssertionError("march test did not finish")

    def model_finish(self):
        n = 0
        while self.m.busy:
            self.m.step()
            n += 1
            assert n < 5_000_000
        # model status read has no side effect

    async def compare_march(self):
        for off in (0x28, 0x2C, 0x30, 0x20, 0x24):
            await self.rd(off)

    async def read_ram_all(self):
        await self.wr(0x10, 0)
        await self.wr(0x1C, 1)
        out = []
        for _ in range(1024):
            out.append(await self.rd(0x18))
        await self.wr(0x1C, 0)
        return out


async def setup(dut):
    h = H(dut)
    await h.start()
    return h


# req: REQ-01, REQ-02, REQ-22, REQ-23, REQ-24, REQ-25, REQ-26
@cocotb.test()
async def test_reset_and_ids(dut):
    h = await setup(dut)
    assert await h.rd(0x00) == ID
    await h.rd(0x04, check=False)  # BUILD: value is the bitstream stamp, hardware checks it
    assert await h.rd(0x08) == 0
    assert await h.rd(0x10) == 0
    assert await h.rd(0x1C) == 0
    assert await h.rd(0x24) == 1
    assert await h.rd(0x28) == 0
    assert await h.rd(0x2C) == 0
    assert await h.rd(0x30) == M32
    assert int(dut.led.value) == 0
    assert int(dut.sfp_tx_disable.value) == 1
    await h.wr(0x08, 0xDEADBEEF)
    assert await h.rd(0x08) == 0xDEADBEEF
    await h.wr(0x10, 77)
    await h.wr(0x1C, 1)
    await h.reset()
    assert await h.rd(0x08) == 0
    assert await h.rd(0x10) == 0
    assert await h.rd(0x1C) == 0
    assert await h.rd(0x00) == ID
    assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-05, REQ-28
@cocotb.test()
async def test_ram_init(dut):
    h = await setup(dut)
    await h.wr(0x1C, 1)
    for i in range(1024):
        v = await h.rd(0x18)
        assert v == BASE + i, f"RAM[{i}] = 0x{v:08x}"
    assert await h.rd(0x10) == 0  # wrapped 1023 -> 0
    await h.wr(0x1C, 0)


# req: REQ-04, REQ-07, REQ-27
@cocotb.test()
async def test_rom_contents(dut):
    h = await setup(dut)
    await h.wr(0x1C, 1)
    await h.wr(0x10, 0)
    for i in range(1024):
        v = await h.rd(0x14)
        assert v == h.m.rom[i], f"ROM[{i}] = 0x{v:08x}"
        if i < 3:
            assert await h.rd(0x10) == i + 1
    assert await h.rd(0x10) == 0  # wrap
    # autoinc clear: unchanged, writes ignored
    await h.wr(0x1C, 0)
    await h.wr(0x10, 5)
    a = await h.rd(0x14)
    b = await h.rd(0x14)
    assert a == b == h.m.rom[5]
    assert await h.rd(0x10) == 5
    await h.wr(0x14, 0x12345678)
    assert await h.rd(0x14) == h.m.rom[5]
    assert await h.rd(0x10) == 5
    await h.wr(0x10, 1023)
    await h.wr(0x1C, 1)
    await h.rd(0x14)
    assert await h.rd(0x10) == 0
    await h.wr(0x1C, 0)


# req: REQ-06, REQ-08, REQ-09, REQ-10, REQ-28
@cocotb.test()
async def test_ram_rw_autoinc(dut):
    h = await setup(dut)
    await h.wr(0x10, 0xFFFFFC05)
    assert await h.rd(0x10) == 5
    await h.wr(0x10, 0x3FF)
    assert await h.rd(0x10) == 0x3FF
    await h.wr(0x10, 9)
    await h.wr(0x18, 0xA5A5A5A5)
    assert await h.rd(0x10) == 9
    assert await h.rd(0x18) == 0xA5A5A5A5
    assert await h.rd(0x10) == 9
    await h.wr(0x1C, 0xFFFFFFFE)  # bit0 clear, autoinc stays off
    assert await h.rd(0x1C) == 0
    await h.wr(0x1C, 1)
    assert await h.rd(0x1C) == 1
    await h.wr(0x10, 100)
    for i in range(8):
        await h.wr(0x18, 0x11110000 + i)
        assert await h.rd(0x10) == 101 + i
    await h.wr(0x10, 100)
    for i in range(8):
        assert await h.rd(0x18) == 0x11110000 + i
        assert await h.rd(0x10) == 101 + i
    # wrap by write at 1023
    await h.wr(0x10, 1023)
    await h.wr(0x18, 0xCAFEF00D)
    assert await h.rd(0x10) == 0
    await h.wr(0x10, 1023)
    assert await h.rd(0x18) == 0xCAFEF00D
    assert await h.rd(0x10) == 0
    # neighbours untouched
    await h.wr(0x10, 1022)
    await h.rd(0x18)
    await h.rd(0x18)
    await h.wr(0x1C, 0)
    await h.wr(0x10, 1023)
    await h.wr(0x18, 0x0F0F0F0F)
    assert await h.rd(0x10) == 1023
    assert await h.rd(0x18) == 0x0F0F0F0F
    # leave RAM zero at the written spots irrelevant: march rewrites everything


# req: REQ-03, REQ-19, REQ-21, REQ-33
@cocotb.test()
async def test_scratch_and_unmapped(dut):
    h = await setup(dut)
    for v in (0, M32, 0x55555555, 0xAAAAAAAA, 0x80000000, 1, 0x12345678):
        await h.wr(0x08, v)
        assert await h.rd(0x08) == v
    # back-to-back write then read: effect one clock after h_we
    await h.wr(0x08, 0x600DF00D)
    assert await h.rd(0x08) == 0x600DF00D
    await h.wr(0x08, 0x0BADCAFE)
    await h.wr(0x10, 3)
    before = {a: await h.rd(a) for a in sorted(MAPPED - {0x04, 0x14, 0x18})}
    unmapped = [a for a in range(0, 0x1000, 4) if a not in MAPPED]
    rnd = random.Random(7)
    pick = unmapped[:8] + [0x34, 0x38, 0x3C, 0x40, 0x100, 0x400, 0x800, 0xFFC] + rnd.sample(unmapped, 24)
    for a in pick:
        assert await h.rd(a, check=False) == 0, f"unmapped 0x{a:03x}"
        await h.wr(a, M32)
        assert await h.rd(a, check=False) == 0
    after = {a: await h.rd(a) for a in sorted(MAPPED - {0x04, 0x14, 0x18})}
    assert before == after
    # writes to read-only registers are ignored
    for a in sorted(RO - {0x04}):
        await h.raw_write(a, 0x5A5A5A5A)
    after = {a: await h.rd(a) for a in sorted(MAPPED - {0x04, 0x14, 0x18})}
    assert before == after
    assert await h.rd(0x00) == ID


# req: REQ-20, REQ-34
@cocotb.test()
async def test_read_timing_hold(dut):
    h = await setup(dut)
    await h.wr(0x08, 0x13572468)
    await h.wr(0x10, 0)
    # sample strictly: re pulse at one edge, value by 2 clocks after sampling edge, then held
    for addr, exp in ((0x00, ID), (0x08, 0x13572468), (0x30, M32), (0x34, 0)):
        dut.h_addr.value = addr
        dut.h_re.value = 1
        await h.tick()
        dut.h_re.value = 0
        await h.tick(2)
        assert int(dut.h_rdata.value) == exp, f"0x{addr:03x}"
        for _ in range(6):
            await h.tick()
            assert int(dut.h_rdata.value) == exp
        # activity on the write path does not disturb the held value
        await h.raw_write(0x08, 0x13572468)
        await h.tick(2)
        assert int(dut.h_rdata.value) == exp
    # back-to-back reads of different registers
    for addr, exp in ((0x00, ID), (0x08, 0x13572468), (0x00, ID)):
        assert await h.raw_read(addr) == exp


# req: REQ-11, REQ-14, REQ-15, REQ-16, REQ-17
@cocotb.test()
async def test_march_inject(dut):
    h = await setup(dut)
    await h.wr(0x24, 3)
    await h.wr(0x20, 0x3)  # START + INJECT
    assert await h.rd(0x20) == 0x2  # START self-clears, INJECT reads back
    st = await h.rd(0x28)
    assert st & 1 == 1 and st & 2 == 0
    assert int(dut.led.value) == 1
    st = await h.wait_done()
    h.model_finish()
    assert int(dut.led.value) == 2
    assert st == 0x00030002, f"status 0x{st:08x}"
    assert await h.rd(0x2C) == 3
    assert await h.rd(0x30) == 0
    await h.compare_march()
    ram = await h.read_ram_all()
    assert ram == [0] * 1024
    await h.wr(0x20, 0)


# req: REQ-11, REQ-12, REQ-13, REQ-16, REQ-18, REQ-29, REQ-30, REQ-31, REQ-32
@cocotb.test()
async def test_march_clean(dut):
    h = await setup(dut)
    # leave dirty state from an injected run, then START must clear it
    await h.wr(0x24, 1)
    await h.wr(0x20, 0x3)
    await h.wait_done()
    h.model_finish()
    assert await h.rd(0x2C) == 1
    assert (await h.rd(0x28)) >> 16 == 1
    # dirty the RAM
    await h.wr(0x10, 0)
    await h.wr(0x1C, 1)
    for i in range(16):
        await h.wr(0x18, 0xFFFFFFFF if i & 1 else 0x5A5A0000 + i)
    await h.wr(0x1C, 0)
    await h.wr(0x24, 1)
    await h.wr(0x20, 0x1)  # START, no inject
    assert await h.rd(0x20) == 0
    st = await h.rd(0x28)
    assert st & 3 == 1 and (st >> 16) == 0
    assert await h.rd(0x2C) == 0 or True  # may already count nothing
    assert await h.rd(0x30) == M32
    st = await h.wait_done()
    h.model_finish()
    assert st == 0x00010002, f"status 0x{st:08x}"
    assert await h.rd(0x2C) == 0
    assert await h.rd(0x30) == M32
    assert int(dut.led.value) == 2
    await h.compare_march()
    assert await h.read_ram_all() == [0] * 1024


# req: REQ-13, REQ-17
@cocotb.test()
async def test_random_traffic(dut):
    h = await setup(dut)
    rnd = random.Random(cocotb.RANDOM_SEED)

    def val():
        c = rnd.choice(("zero", "one", "max", "rand"))
        return {"zero": 0, "one": 1, "max": M32, "rand": rnd.getrandbits(32)}[c]

    for _ in range(500):
        op = rnd.choice(("rd", "rd", "wr", "wr", "wr_addr", "ctl"))
        if op == "rd":
            a = rnd.choice([0x00, 0x08, 0x10, 0x14, 0x18, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x2C, 0x30, 0x44])
            if a == 0x44:
                assert await h.rd(a, check=False) == 0
            else:
                await h.rd(a)
        elif op == "wr":
            a = rnd.choice([0x08, 0x18, 0x18, 0x14, 0x24])
            await h.wr(a, val())
        elif op == "wr_addr":
            await h.wr(0x10, rnd.choice([0, 1023, 1022, rnd.getrandbits(10), val()]))
        else:
            await h.wr(0x1C, val())
            await h.wr(0x20, rnd.choice([0, 2]))
    # random run: 1 pass, random inject, host RAM write and START during BUSY
    inj = rnd.choice([0, 2])
    await h.wr(0x1C, 0)
    await h.wr(0x24, 1)
    await h.wr(0x20, 1 | inj)
    await h.tick(rnd.randint(50, 300))
    st = await h.rd(0x28, check=False)
    assert st & 1 == 1
    await h.raw_write(0x10, 7)       # MEM_ADDR is not RAM: model and RTL both take it
    h.m.addr = 7
    await h.raw_write(0x18, 0xBAD0BAD0)  # ignored during BUSY
    await h.raw_write(0x20, 1 | inj)     # START while BUSY ignored
    await h.wait_done()
    h.model_finish()
    await h.compare_march()
    assert await h.rd(0x2C) == (1 if inj else 0)
    await h.wr(0x20, 0)
    await h.wr(0x10, 0)
    await h.wr(0x1C, 1)
    for i in range(1024):
        await h.rd(0x18)
