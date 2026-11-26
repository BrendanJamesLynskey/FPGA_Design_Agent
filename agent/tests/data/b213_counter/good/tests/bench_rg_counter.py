import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

import model


async def drive(dut, m, **kw):
    """One clock: drive the inputs, step the model with the same inputs, compare after the edge."""
    for k, v in kw.items():
        getattr(dut, k).value = v
    out = m.step(kw)
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(dut.q.value) == out["q"], f"q: rtl {int(dut.q.value):#x} model {out['q']:#x} after {kw}"
    assert int(dut.wrap.value) == out["wrap"], f"wrap: rtl {int(dut.wrap.value)} model {out['wrap']}"
    await FallingEdge(dut.clk)


@cocotb.test()
async def directed(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    m = model.Model()
    dut.rst.value, dut.en.value, dut.load.value, dut.d.value = 1, 0, 0, 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    m.reset()
    await drive(dut, m, en=0, load=0, d=0)
    for _ in range(10):
        await drive(dut, m, en=1, load=0, d=0)
    await drive(dut, m, en=0, load=1, d=0x10)
    await drive(dut, m, en=1, load=1, d=0x20)        # load wins over enable
    await drive(dut, m, en=0, load=1, d=0xF0)        # a plain load of 0xF0
    for _ in range(5):
        await drive(dut, m, en=1, load=0, d=0)
    await drive(dut, m, en=0, load=1, d=0xFE)
    for _ in range(4):                                # wrap
        await drive(dut, m, en=1, load=0, d=0)
