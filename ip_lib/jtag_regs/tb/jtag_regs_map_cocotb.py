"""cocotb bench of jtag_regs_map: drives the register port (h_*) the way jtag_bus does and checks the common map and the pass-through."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

ID = 0x20920001
USR = 0xCAFE1234


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst.value, dut.h_we.value, dut.h_re.value, dut.h_addr.value, dut.h_wdata.value = 1, 0, 0, 0, 0
    dut.usr_access.value, dut.u_rdata.value = USR, 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def wr(dut, a, v):
    dut.h_addr.value, dut.h_wdata.value, dut.h_we.value = a, v, 1
    await RisingEdge(dut.clk)
    dut.h_we.value = 0
    await RisingEdge(dut.clk)


async def rd(dut, a):
    dut.h_addr.value, dut.h_re.value = a, 1
    await RisingEdge(dut.clk)
    dut.h_re.value = 0
    await RisingEdge(dut.clk)
    return int(dut.h_rdata.value)


@cocotb.test()
async def common_map(dut):
    await setup(dut)
    assert await rd(dut, 0x000) == ID
    assert await rd(dut, 0x004) == USR
    assert await rd(dut, 0x008) == 0
    for v in (0xA5A5A5A5, 0x5A5A5A5A, 0xFFFFFFFF, 0):
        await wr(dut, 0x008, v)
        assert await rd(dut, 0x008) == v
    await wr(dut, 0x000, 0x1)                    # ID and BUILD are read-only
    await wr(dut, 0x004, 0x1)
    assert await rd(dut, 0x000) == ID and await rd(dut, 0x004) == USR
    assert await rd(dut, 0x00C) == 0              # unmapped, below the design's registers: reads 0


@cocotb.test()
async def design_registers_pass_through(dut):
    await setup(dut)
    dut.u_rdata.value = 0xDEADBEEF
    assert await rd(dut, 0x010) == 0xDEADBEEF
    assert await rd(dut, 0x7FC) == 0xDEADBEEF
    seen = []
    dut.h_addr.value, dut.h_wdata.value, dut.h_we.value = 0x014, 0x1234, 1
    await RisingEdge(dut.clk)
    seen.append((int(dut.u_we.value), int(dut.u_addr.value), int(dut.u_wdata.value)))
    dut.h_we.value = 0
    dut.h_addr.value, dut.h_wdata.value, dut.h_we.value = 0x008, 0x55, 1      # a scratch write must NOT reach the design
    await RisingEdge(dut.clk)
    seen.append(int(dut.u_we.value))
    dut.h_we.value = 0
    assert seen == [(1, 0x014, 0x1234), 0], seen


@cocotb.test()
async def reset_clears_scratch(dut):
    await setup(dut)
    await wr(dut, 0x008, 0x77)
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    assert await rd(dut, 0x008) == 0
