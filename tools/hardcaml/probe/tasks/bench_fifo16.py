import cocotb
from bench_common import run


@cocotb.test()
async def t(dut):
    await run(dut, "fifo16")
