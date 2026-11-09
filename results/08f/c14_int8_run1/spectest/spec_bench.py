import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

import spec_ref
from shell.tests.uart_bfm import UartBfm
from shell.host import protocol as p

CPB = 16
PARAMS = {"CLKS_PER_BIT": CPB}


async def start(dut):
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, unit="ns").start())
    dut.UART_TXD_IN.value = 1
    dut.CPU_RESETN.value = 0
    await ClockCycles(dut.CLK100MHZ, 10)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 10)
    return UartBfm(dut.CLK100MHZ, dut.UART_TXD_IN, dut.UART_RXD_OUT, CPB)


async def rd(bfm, addr):
    return p.decode_response(await bfm.transact(p.encode_request(p.CMD_READ, addr)))


async def wr(bfm, addr, val):
    return p.decode_response(await bfm.transact(p.encode_request(p.CMD_WRITE, addr, val)))


@cocotb.test()
async def design_id_reads_DOTQ(dut):
    # "The design ID is DOTQ"; PROTOCOL: four ASCII chars, MSB first
    bfm = await start(dut)
    r = await rd(bfm, p.REG_DESIGN_ID)
    assert r.ok and r.data == 0x444F5451, f"expected DESIGN_ID 'DOTQ'=0x444F5451, got status {r.status} data 0x{r.data:08X}"


@cocotb.test()
async def shell_version_and_scratch(dut):
    bfm = await start(dut)
    r = await rd(bfm, p.REG_SHELL_VERSION)
    assert r.ok and r.data == 0x00010000, f"expected SHELL_VERSION 0x00010000, got 0x{r.data:08X}"
    r = await rd(bfm, p.REG_SCRATCH)
    assert r.ok and r.data == 0, f"expected SCRATCH reset 0, got 0x{r.data:08X}"
    r = await wr(bfm, p.REG_SCRATCH, 0x12345678)
    assert r.ok and r.data == 0x12345678, "expected write echo of 0x12345678"
    r = await rd(bfm, p.REG_SCRATCH)
    assert r.data == 0x12345678, f"expected SCRATCH readback 0x12345678, got 0x{r.data:08X}"


@cocotb.test()
async def design_id_is_read_only(dut):
    bfm = await start(dut)
    r = await wr(bfm, p.REG_DESIGN_ID, 0)
    assert r.status == p.ST_READ_ONLY, f"expected READ_ONLY (4) writing DESIGN_ID, got {r.status}"


@cocotb.test()
async def ready_led_low_after_reset(dut):
    # "CPU_RESETN clears ... the ready flag"; "LED0 shows the ready flag"
    bfm = await start(dut)
    await ClockCycles(dut.CLK100MHZ, 5)
    assert int(dut.LED.value) & 1 == 0, "expected LED0 (ready) = 0 after reset with no go issued"


@cocotb.test()
async def window_access_never_shell_error(dut):
    # PROTOCOL: window 0x80-0xFF never an error from the shell; spec registers lie at offsets 0x00-0x0A
    bfm = await start(dut)
    for off in range(0x0B):
        r = await rd(bfm, 0x80 + off)
        assert r.ok, f"expected OK reading window offset 0x{off:02X}, got status {r.status}"


@cocotb.test()
async def model_rounding_and_clamp_examples(dut):
    # Request examples: 2.5 -> 3, -2.5 -> -2; limits -128..127, relu 0..127
    R = spec_ref.requant
    assert R(5, 1, 1, 0) == 3
    assert R(-5, 1, 1, 0) == -2
    assert R(10**6, 1000, 1, 0) == 127
    assert R(-10**6, 1000, 1, 0) == -128
    assert R(-10**6, 1000, 1, 1) == 0
    assert spec_ref.dot_requant([-128] * 8, [-127] * 8, 0, 1, 1, 0)[1] == 8 * 128 * 127
