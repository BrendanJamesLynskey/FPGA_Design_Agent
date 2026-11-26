import random
import sys
import zlib
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

ID, SCRATCH, CTRL, PUSH4, PUSHN, TAIL, CRC, BYTES, BUSY = 0, 8, 16, 20, 24, 28, 32, 36, 40
M32 = 0xFFFFFFFF


async def cyc(dut, we=0, re=0, addr=0, wdata=0):
    dut.h_we.value = we
    dut.h_re.value = re
    dut.h_addr.value = addr
    dut.h_wdata.value = wdata
    await RisingEdge(dut.clk)
    await Timer(1, "ns")


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    dut.rst.value = 1
    for _ in range(8):
        await RisingEdge(dut.clk)
    await Timer(1, "ns")
    dut.rst.value = 0
    await cyc(dut)
    m = model.Model()
    m.reset()
    return m


async def wr(dut, m, addr, val):
    await cyc(dut, we=1, addr=addr, wdata=val)
    await cyc(dut)
    m.write_reg(addr, val)


async def rd(dut, addr):
    await cyc(dut, re=1, addr=addr)
    await cyc(dut)
    return int(dut.h_rdata.value)


async def chk(dut, m, addr, what=""):
    got = await rd(dut, addr)
    exp = m.read_reg(addr)
    assert got == exp, f"{what} addr {addr}: got {got:#x} expected {exp:#x}"
    return got


async def send(dut, m, data, gap=False):
    """INIT, push message (words via PUSH4, tail via PUSH_N); returns nothing."""
    await wr(dut, m, CTRL, 1)
    i = 0
    while len(data) - i >= 4:
        w = int.from_bytes(data[i:i + 4], "little")
        await cyc(dut, we=1, addr=PUSH4, wdata=w)
        m.write_reg(PUSH4, w)
        if gap:
            await cyc(dut)
        i += 4
    await cyc(dut)
    rem = len(data) - i
    if rem:
        await wr(dut, m, TAIL, rem)
        w = int.from_bytes(data[i:] + b"\0" * (4 - rem), "little") | (random.getrandbits(32) & ~((1 << (8 * rem)) - 1) & M32)
        # upper bytes are garbage and must be ignored
        await cyc(dut, we=1, addr=PUSHN, wdata=w)
        await cyc(dut)
        m.write_reg(PUSHN, w)


async def check_msg(dut, m, data, gap=False):
    await send(dut, m, data, gap)
    crc = await rd(dut, CRC)
    assert crc == zlib.crc32(bytes(data)), f"len {len(data)} crc {crc:#x} != {zlib.crc32(bytes(data)):#x}"
    assert crc == m.read_reg(CRC)
    assert await rd(dut, BYTES) == len(data) == m.read_reg(BYTES)
    assert await rd(dut, BUSY) == m.read_reg(BUSY)


# req: REQ-12, REQ-24, REQ-02, REQ-19, REQ-03, REQ-10
@cocotb.test()
async def test_reset_values(dut):
    m = await setup(dut)
    assert await rd(dut, ID) == 0x20930001
    for a in (SCRATCH, CTRL, TAIL, CRC, BYTES, BUSY, PUSH4, PUSHN):
        assert await rd(dut, a) == 0, f"reset value at {a}"
        await chk(dut, m, a, "reset")
    if hasattr(dut, "sfp_tx_disable"):
        assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-19
@cocotb.test()
async def test_sfp_tx_disable(dut):
    m = await setup(dut)
    if hasattr(dut, "sfp_tx_disable"):
        for i in range(50):
            assert int(dut.sfp_tx_disable.value) == 1
            await cyc(dut, we=i & 1, addr=random.choice([8, 20, 16]), wdata=random.getrandbits(32))
        await cyc(dut)
        assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-13, REQ-18, REQ-20, REQ-21
@cocotb.test()
async def test_build_and_structure(dut):
    # BUILD is the USR_ACCESSE2 word (hardware value); in simulation check
    # it is a stable read-only register at 0x004 on the core's register port.
    # Timing (REQ-18), GT count (REQ-20) and jtag_bus instantiation (REQ-21)
    # are discharged by flow analysis gates; the core is exercised here with
    # no GT/transceiver port and a constant sfp_tx_disable.
    m = await setup(dut)
    # BUILD may be X in simulation (USR_ACCESSE2 stand-in); compare raw values.
    async def rd_raw(addr):
        await cyc(dut, re=1, addr=addr)
        await cyc(dut)
        return str(dut.h_rdata.value)

    b0 = await rd_raw(4)
    await wr(dut, m, 4, 0xFFFFFFFF)
    assert await rd_raw(4) == b0
    assert await rd_raw(4) == b0
    if hasattr(dut, "sfp_tx_disable"):
        assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-02, REQ-10, REQ-11
@cocotb.test()
async def test_init(dut):
    m = await setup(dut)
    assert await rd(dut, CRC) == 0
    await wr(dut, m, TAIL, 2)
    await cyc(dut, we=1, addr=PUSH4, wdata=0x11223344)
    m.write_reg(PUSH4, 0x11223344)
    await cyc(dut)
    assert await rd(dut, CRC) != 0
    await cyc(dut, we=1, addr=CTRL, wdata=0xFFFFFFFF)
    m.write_reg(CTRL, 0xFFFFFFFF)
    await cyc(dut)
    assert await rd(dut, CTRL) == 0
    assert await rd(dut, CRC) == 0
    assert await rd(dut, BYTES) == 0
    assert await rd(dut, BUSY) == 0
    # INIT with bit 0 clear does nothing
    await cyc(dut, we=1, addr=PUSH4, wdata=1)
    m.write_reg(PUSH4, 1)
    await cyc(dut)
    await wr(dut, m, CTRL, 0xFFFFFFFE)
    assert await rd(dut, BYTES) == 4
    await chk(dut, m, CRC)
    assert await rd(dut, CTRL) == 0


# req: REQ-04, REQ-01, REQ-03, REQ-08
@cocotb.test()
async def test_lengths(dut):
    m = await setup(dut)
    random.seed(7)
    for n in (0, 1, 2, 3, 4, 5, 7, 8, 63, 64, 65):
        await check_msg(dut, m, bytes(random.getrandbits(8) for _ in range(n)))
    await check_msg(dut, m, b"123456789")
    assert await rd(dut, CRC) == 0xCBF43926


# req: REQ-05
@cocotb.test()
async def test_byte_order(dut):
    m = await setup(dut)
    await wr(dut, m, CTRL, 1)
    await cyc(dut, we=1, addr=PUSH4, wdata=0x04030201)
    m.write_reg(PUSH4, 0x04030201)
    await cyc(dut)
    assert await rd(dut, CRC) == zlib.crc32(bytes([1, 2, 3, 4]))
    assert await rd(dut, CRC) != zlib.crc32(bytes([4, 3, 2, 1]))
    await wr(dut, m, CTRL, 1)
    await wr(dut, m, TAIL, 2)
    await cyc(dut, we=1, addr=PUSHN, wdata=0xAABB0201)
    m.write_reg(PUSHN, 0xAABB0201)
    await cyc(dut)
    assert await rd(dut, CRC) == zlib.crc32(bytes([1, 2]))


# req: REQ-06, REQ-07, REQ-23
@cocotb.test()
async def test_push_n(dut):
    m = await setup(dut)
    await wr(dut, m, CTRL, 1)
    await cyc(dut, we=1, addr=PUSH4, wdata=0xDEADBEEF)
    m.write_reg(PUSH4, 0xDEADBEEF)
    await cyc(dut)
    c0 = await rd(dut, CRC)
    # TAIL_LEN 0
    await cyc(dut, we=1, addr=PUSHN, wdata=0x12345678)
    await cyc(dut)
    assert await rd(dut, CRC) == c0
    assert await rd(dut, BYTES) == 4
    assert await rd(dut, BUSY) == 1
    # tail above 3 ignored
    await wr(dut, m, TAIL, 2)
    for bad in (4, 5, 7, 0x100, 0xFFFFFFFF, 0x102):
        await wr(dut, m, TAIL, bad)
        assert await rd(dut, TAIL) == 2
    await wr(dut, m, TAIL, 0xFFFFFFFE & 0x3)
    for t in (1, 2, 3):
        await wr(dut, m, CTRL, 1)
        await wr(dut, m, TAIL, t)
        assert await rd(dut, TAIL) == t
        v = random.getrandbits(32)
        await cyc(dut, we=1, addr=PUSHN, wdata=v)
        m.write_reg(PUSHN, v)
        await cyc(dut)
        assert await rd(dut, CRC) == zlib.crc32(v.to_bytes(4, "little")[:t])
        assert await rd(dut, BYTES) == t
        assert await rd(dut, BUSY) == 1
        await chk(dut, m, CRC)
    # push after PUSH_N keeps accumulating
    await cyc(dut, we=1, addr=PUSH4, wdata=0x01020304)
    m.write_reg(PUSH4, 0x01020304)
    await cyc(dut)
    await chk(dut, m, CRC)
    await chk(dut, m, BYTES)
    await chk(dut, m, BUSY)


# req: REQ-08, REQ-09, REQ-17, REQ-03, REQ-01
@cocotb.test()
async def test_back_to_back(dut):
    m = await setup(dut)
    random.seed(11)
    for n in (1, 2, 5, 16, 33):
        await wr(dut, m, CTRL, 1)
        words = [random.getrandbits(32) for _ in range(n)]
        for w in words:
            await cyc(dut, we=1, addr=PUSH4, wdata=w)
            m.write_reg(PUSH4, w)
        await cyc(dut)
        data = b"".join(w.to_bytes(4, "little") for w in words)
        assert await rd(dut, CRC) == zlib.crc32(data)
        assert await rd(dut, BUSY) == n
        assert await rd(dut, BYTES) == 4 * n
    # mixed consecutive writes: scratch, push, push, tail, pushn
    await wr(dut, m, CTRL, 1)
    seq = [(SCRATCH, 5), (PUSH4, 0x01020304), (PUSH4, 0x05060708), (TAIL, 3), (PUSHN, 0xFFA1B2C3)]
    for a, v in seq:
        await cyc(dut, we=1, addr=a, wdata=v)
        m.write_reg(a, v)
    await cyc(dut)
    for a in (SCRATCH, CRC, BYTES, BUSY, TAIL):
        await chk(dut, m, a, "mixed")
    # write takes effect by the next clock
    await cyc(dut, we=1, addr=SCRATCH, wdata=0xCAFEF00D)
    await cyc(dut, re=1, addr=SCRATCH)
    await cyc(dut)
    assert int(dut.h_rdata.value) == 0xCAFEF00D


# req: REQ-12, REQ-14, REQ-22, REQ-24, REQ-15, REQ-25
@cocotb.test()
async def test_registers(dut):
    m = await setup(dut)
    for v in (0, M32, 0xA5A5A5A5, 0x5A5A5A5A, 1, 0x80000000):
        await wr(dut, m, SCRATCH, v)
        assert await rd(dut, SCRATCH) == v
    await wr(dut, m, SCRATCH, 0x1234)
    # RO writes ignored
    for a in (0, 32, 36, 40):
        before = await rd(dut, a)
        await wr(dut, m, a, 0xFFFFFFFF)
        assert await rd(dut, a) == before, f"RO write at {a}"
    assert await rd(dut, ID) == 0x20930001
    # unmapped: read 0, write no effect
    await wr(dut, m, TAIL, 3)
    await wr(dut, m, CTRL, 1)
    await cyc(dut, we=1, addr=PUSH4, wdata=0x01010101)
    m.write_reg(PUSH4, 0x01010101)
    await cyc(dut)
    snap = {a: await rd(dut, a) for a in (SCRATCH, TAIL, CRC, BYTES, BUSY, CTRL)}
    unm = [12, 44, 48, 60, 64, 0x100, 0x7FC, 0xFFC, 0x408, 0x810, 0x814, 0x818, 0x81C, 0x820, 0x400, 0x404, 1, 9, 17, 21, 33]
    for a in unm:
        assert await rd(dut, a) == 0, f"unmapped read {a:#x}"
        await cyc(dut, we=1, addr=a, wdata=0xFFFFFFFF)
        await cyc(dut)
    for a, v in snap.items():
        assert await rd(dut, a) == v, f"unmapped write changed {a}"
    for a in (PUSH4, PUSHN, 12, 0x30):
        assert await rd(dut, a) == 0
    await wr(dut, m, TAIL, 1)
    assert await rd(dut, TAIL) == 1


# req: REQ-16, REQ-26
@cocotb.test()
async def test_read_hold(dut):
    m = await setup(dut)
    await wr(dut, m, SCRATCH, 0x600DF00D)
    await cyc(dut, re=1, addr=SCRATCH)
    await cyc(dut)
    assert int(dut.h_rdata.value) == 0x600DF00D
    # holds until next h_re, even while other writes occur
    for i in range(10):
        await cyc(dut, we=1, addr=SCRATCH if i == 0 else PUSH4, wdata=0x1111 * i)
        assert int(dut.h_rdata.value) == 0x600DF00D
    await cyc(dut, re=1, addr=ID)
    await cyc(dut)
    assert int(dut.h_rdata.value) == 0x20930001
    for _ in range(5):
        await cyc(dut)
        assert int(dut.h_rdata.value) == 0x20930001
    # consecutive reads
    await cyc(dut, re=1, addr=SCRATCH)
    await cyc(dut, re=1, addr=ID)
    await cyc(dut)
    assert int(dut.h_rdata.value) == 0x20930001


# req: REQ-01, REQ-03, REQ-08, REQ-04, REQ-06, REQ-07, REQ-10, REQ-14, REQ-15, REQ-22, REQ-23
@cocotb.test()
async def test_random_traffic(dut):
    m = await setup(dut)
    random.seed(cocotb.RANDOM_SEED if hasattr(cocotb, "RANDOM_SEED") else 1)
    for k in range(1000):
        n = random.choice([0, 1, 2, 3, 4, 5, 7, 8, 63, 64, 65, random.randrange(0, 70)])
        await check_msg(dut, m, bytes(random.getrandbits(8) for _ in range(n)), gap=random.random() < 0.3)
    # random register ops against the model
    addrs = [0, 4 * 0 + 8, 16, 20, 24, 28, 32, 36, 40, 12, 44, 0x100]
    for _ in range(1500):
        a = random.choice(addrs)
        cls = random.choice(["zero", "one", "max", "rand", "small"])
        v = {"zero": 0, "one": 1, "max": M32, "rand": random.getrandbits(32), "small": random.randrange(0, 6)}[cls]
        if random.random() < 0.5:
            await cyc(dut, we=1, addr=a, wdata=v)
            m.write_reg(a, v)
            if random.random() < 0.5:
                await cyc(dut)
        else:
            await cyc(dut)
            if a == 4:
                continue
            await chk(dut, m, a, "random")
    await cyc(dut)
    for a in (8, 28, 32, 36, 40):
        await chk(dut, m, a, "final")
