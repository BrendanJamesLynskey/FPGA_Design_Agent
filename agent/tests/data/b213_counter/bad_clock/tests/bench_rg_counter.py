"""Seeded bug in the bench (brief 217 item 0): the clock is started inside the first test only. cocotb cancels it when that test ends, so the second
test waits for an edge that never comes and the simulator ends: "Simulator shut down prematurely", with no assertion."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

import model


@cocotb.test()
async def first(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    m = model.Model()
    dut.rst.value, dut.en.value, dut.load.value, dut.d.value = 1, 0, 0, 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    m.reset()
    dut.en.value = 1
    for _ in range(4):
        out = m.step({"en": 1, "load": 0, "d": 0})
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert int(dut.q.value) == out["q"]
        await FallingEdge(dut.clk)


@cocotb.test()
async def second(dut):
    m = model.Model()
    m.reset()
    for _ in range(4):
        await RisingEdge(dut.clk)
        await ReadOnly()
        await FallingEdge(dut.clk)
