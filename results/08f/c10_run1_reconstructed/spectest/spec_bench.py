import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

import spec_ref as ref
from shell.tests.uart_bfm import UartBfm
from shell.host import protocol as p

CPB = 10
PARAMS = {"CLKS_PER_BIT": CPB, "TIMEOUT_CYCLES": 3000, "BUILD_STAMP": 0}
SEEDS = (1,)

BASE = 0x80


async def setup(dut):
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, unit="ns").start())
    dut.UART_TXD_IN.value = 1
    dut.CPU_RESETN.value = 0
    await ClockCycles(dut.CLK100MHZ, 10)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 20)
    return UartBfm(dut.CLK100MHZ, dut.UART_TXD_IN, dut.UART_RXD_OUT, CPB)


async def rd(bfm, addr):
    r = p.decode_response(await bfm.transact(p.encode_request(p.CMD_READ, addr)))
    assert r.status == p.ST_OK, f"read 0x{addr:02X}: expected OK, got {r.status_name}"
    return r.data


async def wr(bfm, addr, val):
    r = p.decode_response(await bfm.transact(p.encode_request(p.CMD_WRITE, addr, val)))
    assert r.status == p.ST_OK, f"write 0x{addr:02X}: expected OK, got {r.status_name}"


async def check_word(bfm, fw, m):
    await wr(bfm, BASE + ref.PTR, m)
    d = await rd(bfm, BASE + ref.DATA)
    got = ref.unpack_data(d)
    exp = ref.word_samples(fw, m)
    assert got == exp, (f"fw=0x{fw:06X} word {m}: expected samples (2m,2m+1)={exp} "
                        f"from DATA[11:0]/[27:16], design gave {got} (raw 0x{d:08X})")


@cocotb.test()
async def design_id_and_reset_values(dut):
    bfm = await setup(dut)
    v = await rd(bfm, 0x00)
    assert v == ref.DESIGN_ID, f"DESIGN_ID expected 0x{ref.DESIGN_ID:08X} ('DDSN'), got 0x{v:08X}"
    for off, name in ((ref.FW, "FW"), (ref.GO, "GO"), (ref.STATUS, "STATUS"),
                      (ref.PTR, "PTR"), (ref.DATA, "DATA")):
        v = await rd(bfm, BASE + off)
        assert v == 0, f"{name} reset value expected 0 (DATA 0 before DONE), got 0x{v:08X}"


@cocotb.test()
async def register_access_rules(dut):
    bfm = await setup(dut)
    await wr(bfm, BASE + ref.FW, 0xFFFFFFFF)
    v = await rd(bfm, BASE + ref.FW)
    assert v == 0x00FFFFFF, f"FW [23:0] RW, [31:24] read 0: expected 0x00FFFFFF, got 0x{v:08X}"
    await wr(bfm, BASE + ref.PTR, 0x123)
    v = await rd(bfm, BASE + ref.PTR)
    assert v == 0x123, f"PTR RW [9:0]: expected 0x123, got 0x{v:08X}"
    await wr(bfm, BASE + ref.STATUS, 1)
    v = await rd(bfm, BASE + ref.STATUS)
    assert v == 0, f"write to RO STATUS ignored: expected 0, got 0x{v:08X}"
    await wr(bfm, BASE + 0x05, 0xDEADBEEF)
    v = await rd(bfm, BASE + 0x05)
    assert v == 0, f"unmapped offset reads 0 and ignores writes: got 0x{v:08X}"
    await wr(bfm, BASE + ref.DATA, 0x55)
    v = await rd(bfm, BASE + ref.GO)
    assert v == 0, f"GO is write-only and reads 0: got 0x{v:08X}"


@cocotb.test()
async def full_recording_matches_model(dut):
    bfm = await setup(dut)
    fw = 0x01A5C3
    await wr(bfm, BASE + ref.FW, fw)
    await wr(bfm, BASE + ref.GO, 1)
    st = await rd(bfm, BASE + ref.STATUS)
    assert st & 1 == 1, f"STATUS.DONE expected 1 after recording 1200 samples, got 0x{st:08X}"
    assert st >> 1 == 0, f"STATUS other bits expected 0, got 0x{st:08X}"
    exp = ref.samples(fw)
    p0 = await rd(bfm, BASE + ref.PTR)
    assert p0 == 0, f"PTR cleared by GO: expected 0, got {p0}"
    for m in range(ref.N_WORDS):
        d = await rd(bfm, BASE + ref.DATA)
        got = ref.unpack_data(d)
        assert got == (exp[2 * m], exp[2 * m + 1]), (
            f"word {m}: expected samples {(exp[2*m], exp[2*m+1])} (2m in [11:0], 2m+1 in [27:16]), "
            f"design gave {got} (raw 0x{d:08X})")
        if m == 2:
            # three DATA reads (m = 0, 1, 2) done, each advances PTR from 0
            pp = await rd(bfm, BASE + ref.PTR)
            assert pp == 3, f"each DATA read advances PTR: after 3 reads expected 3, got {pp}"
    pp = await rd(bfm, BASE + ref.PTR)
    assert pp == ref.N_WORDS, f"PTR after 600 reads expected 600, got {pp}"


@cocotb.test()
async def other_frequencies_sampled_words(dut):
    bfm = await setup(dut)
    for fw in (0x000000, 0x800000, 0xF00001, 0x40A0F3):
        await wr(bfm, BASE + ref.FW, fw)
        await wr(bfm, BASE + ref.GO, 1)
        for m in (0, 1, 2, 137, 411, 598, 599):
            await check_word(bfm, fw, m)


@cocotb.test()
async def go_clears_ptr_and_restarts_from_entry_zero(dut):
    bfm = await setup(dut)
    await wr(bfm, BASE + ref.FW, 0x020000)
    await wr(bfm, BASE + ref.GO, 1)
    for _ in range(3):
        await rd(bfm, BASE + ref.DATA)
    await wr(bfm, BASE + ref.FW, 0x033333)
    await wr(bfm, BASE + ref.GO, 1)
    v = await rd(bfm, BASE + ref.PTR)
    assert v == 0, f"GO clears PTR: expected 0, got {v}"
    d = await rd(bfm, BASE + ref.DATA)
    assert ref.unpack_data(d) == ref.word_samples(0x033333, 0), (
        f"first sample after GO is table entry 0: expected {ref.word_samples(0x033333, 0)}, "
        f"got {ref.unpack_data(d)}")
    await check_word(bfm, 0x033333, 300)


@cocotb.test()
async def reset_clears_loaded_values(dut):
    bfm = await setup(dut)
    await wr(bfm, BASE + ref.FW, 0x012345)
    await wr(bfm, BASE + ref.GO, 1)
    await wr(bfm, BASE + ref.PTR, 5)
    dut.CPU_RESETN.value = 0
    await ClockCycles(dut.CLK100MHZ, 10)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 20)
    for off, name in ((ref.FW, "FW"), (ref.STATUS, "STATUS"), (ref.PTR, "PTR"), (ref.DATA, "DATA")):
        v = await rd(bfm, BASE + off)
        assert v == 0, f"after CPU_RESETN {name} expected 0, got 0x{v:08X}"
