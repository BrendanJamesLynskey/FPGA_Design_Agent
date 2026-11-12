"""cocotb tests of the test shell RTL against the shell model (shell/model/shell_model.py).

Two parameter sets run these (see test_shell_rtl.py): a fast line
(CLKS_PER_BIT = 8, TIMEOUT_CYCLES = 400) for the random and protocol tests,
and the real line (868 clocks a bit = 115200 baud at 100 MHz, 1 ms timeout)
for the bit-timing tests.
"""

from __future__ import annotations

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from shell.host import protocol as p
from shell.model.shell_model import RamWindow, ShellModel
from shell.tests.uart_bfm import UartBfm

DESIGN_ID = 0x5348_4C54   # "SHLT", set in shell_tb_top.sv


async def setup(dut) -> tuple[UartBfm, ShellModel, int, int]:
    cpb = int(dut.CLKS_PER_BIT.value)
    timeout = int(dut.TIMEOUT_CYCLES.value)
    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    bfm = UartBfm(dut.clk, dut.uart_rx, dut.uart_tx, cpb)
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    await ClockCycles(dut.clk, 5)
    return bfm, ShellModel(DESIGN_ID, 0, RamWindow(16), timeout_s=timeout * 10e-9), cpb, timeout


async def check(bfm: UartBfm, model: ShellModel, req: bytes) -> bytes:
    got = await bfm.transact(req)
    want = model.feed(req)
    assert got == want, f"request {req.hex(' ')}: RTL {got.hex(' ')} model {want.hex(' ')}"
    return got


@cocotb.test()
async def fixed_registers_and_worked_bytes(dut):
    bfm, model, _, _ = await setup(dut)
    assert p.decode_response(await check(bfm, model, p.encode_request(p.CMD_READ, 0x00))).data == DESIGN_ID
    assert p.decode_response(await check(bfm, model, p.encode_request(p.CMD_READ, 0x01))).data == 0x0001_0000
    assert p.decode_response(await check(bfm, model, p.encode_request(p.CMD_READ, 0x02))).data == 0
    # The worked bytes in PROTOCOL.md
    assert await check(bfm, model, bytes.fromhex("A5 02 03 78 56 34 12 09")) == bytes.fromhex("5A 00 78 56 34 12 08")
    assert await check(bfm, model, bytes.fromhex("A5 02 00 00 00 00 00 02")) == bytes.fromhex("5A 04 00 00 00 00 04")
    assert await check(bfm, model, bytes.fromhex("A5 01 00 00 00 00 00 00")) == bytes.fromhex("5A 01 00 00 00 00 01")


@cocotb.test()
async def errors_are_answered_and_counted(dut):
    bfm, model, _, _ = await setup(dut)
    bad_chk = p.encode_request(p.CMD_READ, 0x03)[:-1] + b"\x77"
    for req in [bad_chk, p.encode_request(0x07, 0x03), p.encode_request(p.CMD_READ, 0x05),
                p.encode_request(p.CMD_READ, 0x7F), p.encode_request(p.CMD_WRITE, 0x01, 5)]:
        await check(bfm, model, req)
    st = p.decode_response(await check(bfm, model, p.encode_request(p.CMD_READ, p.REG_STATUS))).data
    assert st == 1 | 4 << 8, hex(st)
    await check(bfm, model, p.encode_request(p.CMD_WRITE, p.REG_STATUS, 0xFFFF_FFFF))   # clears
    assert p.decode_response(await check(bfm, model, p.encode_request(p.CMD_READ, p.REG_STATUS))).data == 0


@cocotb.test()
async def sync_hunting_skips_junk(dut):
    bfm, model, _, _ = await setup(dut)
    req = bytes([0x00, 0xFF, 0x5A, 0x13]) + p.encode_request(p.CMD_WRITE, 0x83, 0xDEAD_BEEF)
    await check(bfm, model, req)
    assert p.decode_response(await check(bfm, model, p.encode_request(p.CMD_READ, 0x83))).data == 0xDEAD_BEEF


@cocotb.test()
async def part_frame_times_out_without_answer(dut):
    bfm, model, cpb, timeout = await setup(dut)
    await bfm.send(p.encode_request(p.CMD_READ, 0x00)[:4])
    assert model.feed(p.encode_request(p.CMD_READ, 0x00)[:4]) == b""
    await bfm.expect_silence(timeout + 4 * cpb)
    model.idle((timeout + 4 * cpb) * 10e-9)
    # A gap shorter than the timeout keeps the frame alive
    req = p.encode_request(p.CMD_READ, 0x00)
    await bfm.send(req[:4])
    await ClockCycles(dut.clk, timeout // 2)
    got = await bfm.transact(req[4:])
    assert got == model.feed(req), got.hex(" ")
    st = p.decode_response(await check(bfm, model, p.encode_request(p.CMD_READ, p.REG_STATUS))).data
    assert st == 1 << 24, hex(st)


@cocotb.test()
async def framing_error_drops_the_frame(dut):
    bfm, model, cpb, timeout = await setup(dut)
    req = p.encode_request(p.CMD_WRITE, p.REG_SCRATCH, 0x1111_1111)
    await bfm.send(req[:3])
    await bfm.send_byte(req[3], stop=0)
    model.framing_error()
    await bfm.send(req[4:])        # the rest of the frame is junk to a hunting shell
    assert model.feed(req[4:]) == b""
    await bfm.expect_silence(4 * cpb)
    st = p.decode_response(await check(bfm, model, p.encode_request(p.CMD_READ, p.REG_STATUS))).data
    assert st == 1 << 16, hex(st)
    assert p.decode_response(await check(bfm, model, p.encode_request(p.CMD_READ, p.REG_SCRATCH))).data == 0


@cocotb.test()
async def random_transactions_match_the_model(dut):
    bfm, model, _, _ = await setup(dut)
    rng = random.Random(int(cocotb.RANDOM_SEED))
    addrs = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x40, 0x7F] + list(range(0x80, 0x92)) + [0xC0, 0xFF]
    for _ in range(150):
        cmd = rng.choice([p.CMD_READ, p.CMD_WRITE, p.CMD_WRITE, 0x00, 0x03])
        req = p.encode_request(cmd, rng.choice(addrs), rng.getrandbits(32))
        if rng.random() < 0.05:
            req = req[:-1] + bytes([req[-1] ^ (1 << rng.randrange(8))])   # corrupt the checksum
        await check(bfm, model, req)


@cocotb.test()
async def bit_timing_at_line_rate(dut):
    """Every bit the shell sends lasts exactly CLKS_PER_BIT clocks (868 = 115200 baud at 100 MHz)."""
    bfm, model, cpb, _ = await setup(dut)
    await check(bfm, model, p.encode_request(p.CMD_WRITE, p.REG_SCRATCH, 0x5555_5555))
    runs: list[int] = []
    listener = cocotb.start_soon(_measure_response(bfm, runs))
    await bfm.send(p.encode_request(p.CMD_READ, p.REG_SCRATCH))
    got = await listener
    assert got == model.feed(p.encode_request(p.CMD_READ, p.REG_SCRATCH))
    interior = runs[1:]   # the first run is cut by where sampling starts
    assert interior and all(r % cpb == 0 for r in interior), sorted(set(interior))
    assert cpb in interior   # 0x55 bytes give single-bit runs
    dut._log.info("TX runs (clocks): %s; baud = %.1f", sorted(set(interior)), 100e6 / cpb)


async def _measure_response(bfm: UartBfm, runs: list[int]) -> bytes:
    out = []
    for _ in range(p.RESP_LEN):
        out.append(await bfm.recv_byte(200 * bfm.cpb, measure=runs))
    return bytes(out)


@cocotb.test()
async def receiver_tolerates_two_percent_baud_error(dut):
    bfm, model, cpb, _ = await setup(dut)
    for scale in (0.98, 1.02):
        req = p.encode_request(p.CMD_READ, 0x00)
        listener = cocotb.start_soon(bfm.recv(p.RESP_LEN, 200 * cpb))
        await bfm.send(req, bit_clks=round(cpb * scale))
        assert await listener == model.feed(req)
