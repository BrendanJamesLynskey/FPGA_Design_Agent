"""cocotb bench for the CRC-32 register core, checked against model.py and zlib."""
import random
import sys
import zlib
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model  # noqa: E402

ID, BUILD, SCRATCH, CTRL, PUSH4, PUSH_N, TAIL, CRC, BCNT, BUSY = (
    0x00, 0x04, 0x08, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x28)
CHECKED = [ID, SCRATCH, CTRL, TAIL, CRC, BCNT, BUSY]


async def cyc(dut):
    await RisingEdge(dut.clk)
    await Timer(1, "ns")


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 8, units="ns").start())
    dut.rst.value = 1
    dut.h_we.value = 0
    dut.h_re.value = 0
    dut.h_addr.value = 0
    dut.h_wdata.value = 0
    for _ in range(4):
        await cyc(dut)
    dut.rst.value = 0
    await cyc(dut)
    return model.Model()


async def write(dut, m, addr, val, idle=True):
    dut.h_we.value = 1
    dut.h_addr.value = addr
    dut.h_wdata.value = val
    await cyc(dut)
    dut.h_we.value = 0
    m.write_reg(addr, val)
    if idle:
        await cyc(dut)


async def read(dut, m, addr, check=True):
    dut.h_re.value = 1
    dut.h_addr.value = addr
    await cyc(dut)
    dut.h_re.value = 0
    await cyc(dut)
    got = int(dut.h_rdata.value)
    if check:
        exp = m.read_reg(addr)
        assert got == exp, f"read 0x{addr:03x}: got 0x{got:08x} expected 0x{exp:08x}"
    return got


async def all_regs(dut, m):
    for a in CHECKED:
        await read(dut, m, a)


async def send_msg(dut, m, data, idle=True):
    await write(dut, m, CTRL, 1, idle)
    i = 0
    while len(data) - i >= 4:
        w = int.from_bytes(data[i:i + 4], "little")
        await write(dut, m, PUSH4, w, idle)
        i += 4
    n = len(data) - i
    if n:
        await write(dut, m, TAIL, n, idle)
        w = int.from_bytes(data[i:] + b"\xa5" * (4 - n), "little")
        await write(dut, m, PUSH_N, w, idle)


async def check_msg(dut, m, data):
    crc = await read(dut, m, CRC)
    assert crc == zlib.crc32(bytes(data)) & 0xFFFFFFFF, f"crc len {len(data)}: 0x{crc:08x}"
    assert await read(dut, m, BCNT) == len(data)
    assert await read(dut, m, BUSY) == len(data) // 4 + (1 if len(data) % 4 else 0)


# req: REQ-12, REQ-24, REQ-18
@cocotb.test()
async def test_smoke_reset_values(dut):
    m = await start(dut)
    assert await read(dut, m, ID) == 0x20930001
    assert await read(dut, m, SCRATCH) == 0
    assert await read(dut, m, CRC) == 0
    await all_regs(dut, m)
    if hasattr(dut, "sfp_tx_disable"):
        assert int(dut.sfp_tx_disable.value) == 1


# req: REQ-12, REQ-14, REQ-24
@cocotb.test()
async def test_id_scratch(dut):
    m = await start(dut)
    for v in (0, 1, 0xFFFFFFFF, 0xA5A5A5A5, 0x5A5A5A5A, 0x80000000, 0x12345678):
        await write(dut, m, SCRATCH, v)
        assert await read(dut, m, SCRATCH) == v
        assert await read(dut, m, ID) == 0x20930001
    # RO writes ignored
    for a in (ID, CRC, BCNT, BUSY):  # BUILD is X in simulation (USR_ACCESS stub)
        before = await read(dut, m, a, check=False)
        await write(dut, m, a, 0xDEADBEEF)
        assert await read(dut, m, a, check=False) == before
    await all_regs(dut, m)
    # reset returns scratch to 0
    dut.rst.value = 1
    await cyc(dut)
    await cyc(dut)
    dut.rst.value = 0
    await cyc(dut)
    m.reset()
    assert await read(dut, m, SCRATCH) == 0
    await all_regs(dut, m)


# req: REQ-03, REQ-04, REQ-01, REQ-02, REQ-07
@cocotb.test()
async def test_directed_lengths(dut):
    m = await start(dut)
    await write(dut, m, CTRL, 1)
    assert await read(dut, m, CRC) == 0
    rng = random.Random(7)
    for n in (0, 1, 2, 3, 4, 5, 7, 8, 63, 64, 65):
        data = bytes(rng.randrange(256) for _ in range(n))
        await send_msg(dut, m, data)
        await check_msg(dut, m, data)
    await send_msg(dut, m, b"123456789")
    assert await read(dut, m, CRC) == 0xCBF43926


# req: REQ-05
@cocotb.test()
async def test_push4_byte_order(dut):
    m = await start(dut)
    for w in (0x04030201, 0x01020304, 0x000000FF, 0xFF000000, 0x0000FF00, 0x00FF0000):
        await write(dut, m, CTRL, 1)
        await write(dut, m, PUSH4, w)
        exp = zlib.crc32(w.to_bytes(4, "little"))
        assert await read(dut, m, CRC) == exp
        assert await read(dut, m, CRC) == m.read_reg(CRC)


# req: REQ-06
@cocotb.test()
async def test_push_n_tail(dut):
    m = await start(dut)
    for n in range(4):
        await write(dut, m, CTRL, 1)
        await write(dut, m, TAIL, n)
        assert await read(dut, m, TAIL) == n
        w = 0x44332211
        await write(dut, m, PUSH_N, w)
        exp = zlib.crc32(w.to_bytes(4, "little")[:n]) if n else 0
        assert await read(dut, m, CRC) == exp
        assert await read(dut, m, BCNT) == n
        assert await read(dut, m, BUSY) == (1 if n else 0)
    # tail > 3 stores only bits 1:0
    await write(dut, m, TAIL, 0xFF)
    assert await read(dut, m, TAIL) == 3
    await write(dut, m, TAIL, 4)
    assert await read(dut, m, TAIL) == 0
    await write(dut, m, PUSH_N, 0x11223344)
    await all_regs(dut, m)


# req: REQ-07, REQ-02
@cocotb.test()
async def test_busy_cycles_words(dut):
    m = await start(dut)
    for nw in (1, 2, 5, 16):
        await write(dut, m, CTRL, 1)
        rng = random.Random(nw)
        data = bytes(rng.randrange(256) for _ in range(4 * nw))
        await send_msg(dut, m, data)
        assert await read(dut, m, BUSY) == nw
        assert await read(dut, m, BCNT) == 4 * nw
        assert await read(dut, m, CRC) == zlib.crc32(data)


# req: REQ-08
@cocotb.test()
async def test_throughput_back_to_back(dut):
    m = await start(dut)
    await write(dut, m, CTRL, 1)
    rng = random.Random(3)
    data = bytearray()
    for _ in range(64):
        w = rng.getrandbits(32)
        data += w.to_bytes(4, "little")
        await write(dut, m, PUSH4, w, idle=False)
    await cyc(dut)
    assert await read(dut, m, CRC) == zlib.crc32(bytes(data))
    assert await read(dut, m, BCNT) == 256
    assert await read(dut, m, BUSY) == 64


# req: REQ-09, REQ-21, REQ-22, REQ-10
@cocotb.test()
async def test_init_clears(dut):
    m = await start(dut)
    await send_msg(dut, m, bytes(range(37)))
    assert await read(dut, m, BCNT) == 37
    await write(dut, m, CTRL, 0xFFFFFFFE)  # bit 0 clear: no init
    assert await read(dut, m, BCNT) == 37
    await write(dut, m, CTRL, 1, idle=False)
    dut.h_re.value = 1
    dut.h_addr.value = CTRL
    await cyc(dut)
    dut.h_re.value = 0
    await cyc(dut)
    assert int(dut.h_rdata.value) == 0  # self-clearing
    assert await read(dut, m, CRC) == 0
    assert await read(dut, m, BCNT) == 0
    assert await read(dut, m, BUSY) == 0
    # after INIT a new message starts from the initial state
    await write(dut, m, PUSH4, 0x64636261)
    assert await read(dut, m, CRC) == zlib.crc32(b"abcd")
    await write(dut, m, CTRL, 0xFFFFFFFF)
    assert await read(dut, m, BCNT) == 0
    assert await read(dut, m, CTRL) == 0
    await all_regs(dut, m)


# req: REQ-15, REQ-25
@cocotb.test()
async def test_unmapped_addresses(dut):
    m = await start(dut)
    await write(dut, m, SCRATCH, 0x1234)
    await send_msg(dut, m, b"hello world")
    await write(dut, m, TAIL, 2)
    for a in (0x00C, 0x02C, 0x030, 0x040, 0x100, 0x400, 0x800, 0xFFC):
        assert await read(dut, m, a, check=False) == 0
        await write(dut, m, a, 0xFFFFFFFF)
        await write(dut, m, a, 0x1)
        assert await read(dut, m, a, check=False) == 0
        await all_regs(dut, m)


# req: REQ-16, REQ-26
@cocotb.test()
async def test_read_latency_and_hold(dut):
    m = await start(dut)
    await write(dut, m, SCRATCH, 0xCAFEF00D)
    await write(dut, m, PUSH4, 0x01020304)
    # one pulse
    dut.h_re.value = 1
    dut.h_addr.value = SCRATCH
    await cyc(dut)
    dut.h_re.value = 0
    dut.h_addr.value = CRC  # change address: value must hold
    seen = int(dut.h_rdata.value)
    if seen != 0xCAFEF00D:
        await cyc(dut)
        seen = int(dut.h_rdata.value)
    assert seen == 0xCAFEF00D, "not valid within 2 clocks"
    for _ in range(6):
        await cyc(dut)
        assert int(dut.h_rdata.value) == 0xCAFEF00D
    # changing registers without h_re does not change h_rdata
    await write(dut, m, SCRATCH, 0x11111111)
    await write(dut, m, PUSH4, 0x05060708)
    assert int(dut.h_rdata.value) == 0xCAFEF00D
    # back-to-back reads
    for a in (ID, SCRATCH, CRC, BCNT):
        dut.h_re.value = 1
        dut.h_addr.value = a
        await cyc(dut)
        dut.h_re.value = 0
        await cyc(dut)
        assert int(dut.h_rdata.value) == m.read_reg(a)


# req: REQ-17, REQ-09
@cocotb.test()
async def test_write_latency(dut):
    m = await start(dut)
    # write at cycle t, read request at cycle t+1 sees the new value
    dut.h_we.value = 1
    dut.h_addr.value = SCRATCH
    dut.h_wdata.value = 0xA1B2C3D4
    await cyc(dut)
    dut.h_we.value = 0
    dut.h_re.value = 1
    dut.h_addr.value = SCRATCH
    await cyc(dut)
    dut.h_re.value = 0
    await cyc(dut)
    assert int(dut.h_rdata.value) == 0xA1B2C3D4
    # push then immediate CRC read
    m.write_reg(SCRATCH, 0xA1B2C3D4)
    dut.h_we.value = 1
    dut.h_addr.value = PUSH4
    dut.h_wdata.value = 0x64636261
    await cyc(dut)
    dut.h_we.value = 0
    dut.h_re.value = 1
    dut.h_addr.value = CRC
    await cyc(dut)
    dut.h_re.value = 0
    await cyc(dut)
    assert int(dut.h_rdata.value) == zlib.crc32(b"abcd")


# req: REQ-01, REQ-02, REQ-07
@cocotb.test()
async def test_random_messages(dut):
    m = await start(dut)
    rng = random.Random(cocotb.RANDOM_SEED)
    for k in range(1000):
        n = rng.choice([rng.randrange(0, 12), rng.randrange(0, 70)])
        data = bytes(rng.getrandbits(8) for _ in range(n))
        await send_msg(dut, m, data, idle=rng.random() < 0.5)
        await check_msg(dut, m, data)


# req: REQ-01, REQ-02, REQ-05, REQ-06, REQ-07, REQ-09, REQ-14, REQ-15, REQ-16, REQ-17, REQ-21, REQ-22, REQ-25, REQ-26
@cocotb.test()
async def test_random_traffic(dut):
    m = await start(dut)
    rng = random.Random(cocotb.RANDOM_SEED + 1000)
    addrs = [ID, BUILD, SCRATCH, CTRL, PUSH4, PUSH_N, TAIL, CRC, BCNT, BUSY,
             0x00C, 0x02C, 0x100, 0xFFC]
    for _ in range(3000):
        a = rng.choice(addrs)
        r = rng.random()
        v = rng.choice([0, 1, 0xFFFFFFFF, rng.getrandbits(32)])
        if r < 0.5:
            if a == CTRL and rng.random() < 0.8:
                v &= ~1
            await write(dut, m, a, v, idle=rng.random() < 0.3)
        elif a != BUILD:
            await read(dut, m, a)
    await all_regs(dut, m)
