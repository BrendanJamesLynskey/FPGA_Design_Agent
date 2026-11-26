"""cocotb bench for the CRC-32 register core; every check is against model.py and zlib."""
import random
import sys
import zlib
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402
from model import Model  # noqa: E402

ID, BUILD, SCRATCH, CTRL, PUSH4, PUSH_N, TAIL, CRC, BCNT, BUSY = 0, 4, 8, 16, 20, 24, 28, 32, 36, 40
M32 = 0xFFFFFFFF
RNG = random.Random(1)


def has(dut, name):
    try:
        getattr(dut, name)
        return True
    except AttributeError:
        return False


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.m = Model()

    async def reset(self):
        d = self.dut
        d.h_we.value = 0
        d.h_re.value = 0
        d.h_addr.value = 0
        d.h_wdata.value = 0
        if has(d, "locked"):
            d.locked.value = 1
        d.rst.value = 1
        for _ in range(6):
            await RisingEdge(d.clk)
        d.rst.value = 0
        for _ in range(3):
            await RisingEdge(d.clk)
        self.m.reset()

    async def idle(self, n=1):
        d = self.dut
        d.h_we.value = 0
        d.h_re.value = 0
        for _ in range(n):
            await RisingEdge(d.clk)

    async def write(self, addr, val, gap=2):
        d = self.dut
        d.h_we.value = 1
        d.h_addr.value = addr
        d.h_wdata.value = val
        await RisingEdge(d.clk)
        d.h_we.value = 0
        self.m.write_reg(addr, val)
        await self.idle(gap)

    async def push_burst(self, words):
        """PUSH4 writes on consecutive clocks."""
        d = self.dut
        for w in words:
            d.h_we.value = 1
            d.h_addr.value = PUSH4
            d.h_wdata.value = w
            await RisingEdge(d.clk)
            self.m.write_reg(PUSH4, w)
        d.h_we.value = 0
        await self.idle(3)

    async def read(self, addr):
        d = self.dut
        d.h_re.value = 1
        d.h_addr.value = addr
        await RisingEdge(d.clk)
        d.h_re.value = 0
        await RisingEdge(d.clk)
        await Timer(1, "ns")
        return int(d.h_rdata.value)

    async def check(self, addr, what=""):
        got = await self.read(addr)
        exp = self.m.read_reg(addr)
        assert got == exp, f"{what} reg 0x{addr:x}: got 0x{got:08x} expected 0x{exp:08x}"
        return got

    async def message(self, data: bytes):
        await self.write(CTRL, 1)
        words = [int.from_bytes(data[i:i + 4], "little") for i in range(0, len(data) // 4 * 4, 4)]
        if words:
            await self.push_burst(words)
        tail = data[len(words) * 4:]
        if tail:
            await self.write(TAIL, len(tail))
            await self.write(PUSH_N, int.from_bytes(tail, "little") | (RNG.getrandbits(32) & ~((1 << (8 * len(tail))) - 1) & M32))


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    b = Bench(dut)
    await b.reset()
    return b


# req: REQ-01, REQ-02, REQ-03, REQ-20
@cocotb.test()
async def test_common_regs(dut):
    b = await start(dut)
    # reset values first (SCRATCH resets to 0)
    assert await b.read(SCRATCH) == 0
    assert await b.read(ID) == 0x20930001
    assert (await b.read(ID)) == b.m.read_reg(ID)
    await b.read(BUILD)  # value is the USR_ACCESS word; only read, compared on hardware
    for v in (0xFFFFFFFF, 0, 0xA5A5A5A5, 0x5A5A5A5A, 0x80000001, 0x12345678):
        await b.write(SCRATCH, v)
        await b.check(SCRATCH, "scratch")
    # ID is read-only
    await b.write(ID, 0xDEADBEEF)
    assert await b.read(ID) == 0x20930001
    # reset clears scratch
    await b.write(SCRATCH, 0xCAFEF00D)
    await b.reset()
    assert await b.read(SCRATCH) == 0


# req: REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-10, REQ-11, REQ-23, REQ-24
@cocotb.test()
async def test_crc_directed(dut):
    b = await start(dut)
    # empty message
    await b.write(CTRL, 1)
    assert await b.read(CRC) == 0
    await b.check(BCNT)
    await b.check(BUSY)
    # known vector "123456789" -> 0xCBF43926
    await b.write(CTRL, 1)
    await b.push_burst([int.from_bytes(b"1234", "little"), int.from_bytes(b"5678", "little")])
    await b.write(TAIL, 1)
    await b.write(PUSH_N, ord("9"))
    assert await b.read(CRC) == 0xCBF43926 == zlib.crc32(b"123456789")
    await b.check(CRC)
    assert await b.read(BCNT) == 9
    await b.check(BCNT)
    await b.check(BUSY)
    # back-to-back words: every one accepted
    for n in (1, 2, 3, 8, 17):
        await b.write(CTRL, 1)
        data = bytes(RNG.getrandbits(8) for _ in range(4 * n))
        await b.push_burst([int.from_bytes(data[i:i + 4], "little") for i in range(0, len(data), 4)])
        assert await b.read(CRC) == zlib.crc32(data)
        assert await b.read(BCNT) == 4 * n
        assert await b.read(BUSY) == n
        await b.check(CRC)
    # INIT clears CRC, count, busy; and reads back 0 the clock after
    await b.write(CTRL, 1, gap=0)
    assert await b.read(CTRL) == 0
    assert await b.read(CRC) == 0
    assert await b.read(BCNT) == 0
    assert await b.read(BUSY) == 0
    # write 0 to CTRL does nothing; reserved bits do not clear
    await b.push_burst([0x11223344])
    await b.write(CTRL, 0xFFFFFFFE)
    await b.check(CRC)
    await b.check(BCNT)
    await b.check(BUSY)
    assert await b.read(CTRL) == 0
    # push after init works from init state
    await b.write(CTRL, 1)
    await b.push_burst([0xFFFFFFFF])
    await b.check(CRC)
    # push immediately followed by INIT
    await b.push_burst([0x01020304, 0x05060708])
    await b.write(CTRL, 1)
    assert await b.read(CRC) == 0


# req: REQ-09, REQ-06
@cocotb.test()
async def test_push_n(dut):
    b = await start(dut)
    assert await b.read(TAIL) == 0
    for n in range(4):
        await b.write(CTRL, 1)
        await b.write(TAIL, n)
        assert await b.read(TAIL) == n
        v = RNG.getrandbits(32)
        await b.write(PUSH_N, v)
        data = (v & ((1 << (8 * n)) - 1)).to_bytes(n, "little")
        assert await b.read(CRC) == zlib.crc32(data)
        assert await b.read(BCNT) == n
        await b.check(CRC)
        await b.check(BCNT)
        await b.check(BUSY)
    # N=0: nothing pushed even after earlier data
    await b.write(CTRL, 1)
    await b.push_burst([0xAABBCCDD])
    await b.write(TAIL, 0)
    await b.write(PUSH_N, 0xFFFFFFFF)
    await b.check(CRC)
    await b.check(BCNT)
    await b.check(BUSY)
    # TAIL_LEN masked to two bits
    await b.write(TAIL, 7)
    await b.check(TAIL)
    await b.write(TAIL, 0xFFFFFFFC)
    await b.check(TAIL)
    await b.write(PUSH_N, 0x01020304)
    await b.check(CRC)
    await b.check(BCNT)


# req: REQ-12, REQ-21
@cocotb.test()
async def test_unmapped(dut):
    b = await start(dut)
    await b.write(SCRATCH, 0x13572468)
    await b.write(TAIL, 2)
    await b.push_burst([0xDEADBEEF])
    regs = [ID, SCRATCH, CTRL, PUSH4, PUSH_N, TAIL, CRC, BCNT, BUSY]
    before = [await b.read(r) for r in regs]
    for a in (0x2C, 0x30, 0x34, 0x40, 0x44, 0x80, 0x100, 0x400, 0x800, 0xFFC):
        assert await b.read(a) == 0, f"unmapped 0x{a:x}"
        await b.write(a, 0xFFFFFFFF)
        assert await b.read(a) == 0
    after = [await b.read(r) for r in regs]
    assert before == after, "unmapped write changed a register"
    # WO registers read 0; writes to RO registers ignored
    assert await b.read(PUSH4) == 0
    assert await b.read(PUSH_N) == 0
    for a in (ID, CRC, BCNT, BUSY):
        await b.write(a, 0x12345678)
    assert [await b.read(r) for r in regs] == before
    for r in regs:
        await b.check(r)


# req: REQ-13, REQ-22
@cocotb.test()
async def test_read_hold(dut):
    b = await start(dut)
    d = dut
    await b.write(SCRATCH, 0x0BADF00D)
    await b.write(TAIL, 3)
    # read, then the value is there within 2 clocks and holds
    d.h_re.value = 1
    d.h_addr.value = SCRATCH
    await RisingEdge(d.clk)
    d.h_re.value = 0
    await RisingEdge(d.clk)
    await Timer(1, "ns")
    assert int(d.h_rdata.value) == 0x0BADF00D
    for i in range(12):
        # unrelated writes and pushes must not disturb the held value
        d.h_we.value = 1
        d.h_addr.value = [TAIL, PUSH4, CTRL, SCRATCH][i % 4] if i % 4 != 3 else TAIL
        d.h_wdata.value = RNG.getrandbits(32) & (0xFFFFFFFF if i % 4 != 2 else 0)
        await RisingEdge(d.clk)
        d.h_we.value = 0
        await Timer(1, "ns")
        assert int(d.h_rdata.value) == 0x0BADF00D, f"h_rdata moved at hold cycle {i}"
        await RisingEdge(d.clk)
    # back-to-back reads of different registers
    await b.write(CTRL, 1)
    await b.write(SCRATCH, 0x77)
    await b.write(TAIL, 3)
    for a in (SCRATCH, ID, TAIL, CRC, SCRATCH, 0x200):
        got = await b.read(a)
        m = Model()
        exp = {SCRATCH: 0x77, ID: 0x20930001, TAIL: 3, CRC: 0, 0x200: 0}[a]
        assert got == exp
    # a new read replaces the held value
    assert await b.read(ID) == 0x20930001


# req: REQ-14
@cocotb.test()
async def test_write_latency(dut):
    b = await start(dut)
    d = dut
    for v in (0x11111111, 0xEEEEEEEE):
        d.h_we.value = 1
        d.h_addr.value = SCRATCH
        d.h_wdata.value = v
        await RisingEdge(d.clk)
        # the clock after h_we: read request in the very next cycle sees the new value
        d.h_we.value = 0
        d.h_re.value = 1
        d.h_addr.value = SCRATCH
        await RisingEdge(d.clk)
        d.h_re.value = 0
        await RisingEdge(d.clk)
        await Timer(1, "ns")
        assert int(d.h_rdata.value) == v
        await b.idle(2)
    # TAIL_LEN likewise
    d.h_we.value = 1
    d.h_addr.value = TAIL
    d.h_wdata.value = 2
    await RisingEdge(d.clk)
    d.h_we.value = 0
    d.h_re.value = 1
    d.h_addr.value = TAIL
    await RisingEdge(d.clk)
    d.h_re.value = 0
    await RisingEdge(d.clk)
    await Timer(1, "ns")
    assert int(d.h_rdata.value) == 2


# req: REQ-15, REQ-16, REQ-17, REQ-18
@cocotb.test()
async def test_sfp_disable(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    b = Bench(dut)
    if not has(dut, "sfp_tx_disable"):
        dut._log.info("sfp_tx_disable not on the core; checked on the top by the flow")
        await b.reset()
        return
    seen = []

    async def watch():
        while True:
            await RisingEdge(dut.clk)
            await Timer(1, "ns")
            seen.append(int(dut.sfp_tx_disable.value))

    cocotb.start_soon(watch())
    await b.reset()
    await b.write(SCRATCH, 0)
    await b.push_burst([1, 2, 3])
    await b.write(CTRL, 1)
    await b.idle(20)
    assert seen and all(v == 1 for v in seen)
    if has(dut, "led"):
        assert (int(dut.led.value) >> 1) & 1 == 0, "led[1] must be 0"


# req: REQ-04, REQ-19, REQ-25, REQ-06, REQ-07
@cocotb.test()
async def test_random_messages(dut):
    b = await start(dut)
    seed = int(cocotb.RANDOM_SEED) if hasattr(cocotb, "RANDOM_SEED") else 1
    rng = random.Random(seed)
    fixed = [0, 1, 2, 3, 4, 5, 7, 8, 63, 64, 65]
    for i in range(1000):
        if i < len(fixed):
            n = fixed[i]
        elif i < len(fixed) + 6:
            n = rng.randint(200, 400)
        elif rng.random() < 0.5:
            n = rng.choice(fixed)
        else:
            n = rng.randint(0, 130)
        data = bytes(rng.getrandbits(8) for _ in range(n))
        await b.write(CTRL, 1, gap=rng.choice([0, 1, 2]))
        words = [int.from_bytes(data[k:k + 4], "little") for k in range(0, n // 4 * 4, 4)]
        if words:
            await b.push_burst(words)
        tail = data[len(words) * 4:]
        if tail:
            await b.write(TAIL, len(tail))
            junk = rng.getrandbits(32) & ~((1 << (8 * len(tail))) - 1) & M32
            await b.write(PUSH_N, int.from_bytes(tail, "little") | junk)
        crc = await b.read(CRC)
        assert crc == zlib.crc32(data), f"msg {i} len {n}: crc 0x{crc:08x}"
        cnt = await b.read(BCNT)
        assert cnt == n, f"msg {i} len {n}: count {cnt}"
        if i % 10 == 0:
            await b.check(BUSY, f"msg {i}")
            if n % 4 == 0:
                assert await b.read(BUSY) == n // 4
