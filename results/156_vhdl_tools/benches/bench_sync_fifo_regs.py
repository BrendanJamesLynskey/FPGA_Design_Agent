"""t1_sync_fifo_regs (brief 55 VHDL translation, entity sync_fifo_regs) against the task's golden model (model.py of the dev task)."""
import cocotb
from cocotb.triggers import RisingEdge
from common import Trace, Window, ops, rng, start_clock
from loadmodel import load_model

M = load_model("t1_sync_fifo_regs")


@cocotb.test()
async def fifo_random(dut):
    await start_clock(dut)
    w = Window(dut)
    w.idle()
    tr = Trace("sync_fifo_regs", dut.clk, {"led": dut.led, "rdata": dut.win_rdata})
    await w.reset()
    tr.enabled = True
    m = M.Model()
    r = rng()
    n = ops()
    got = await w.read(M.LEVEL)
    assert got == 0, f"level after reset {got}"
    for i in range(n):
        k = r.random()
        if k < 0.35:
            v = r.randrange(256)
            await w.write(M.PUSH, v)
            m.push(v)
        elif k < 0.65:
            got = await w.read(M.POP)
            want = m.pop()
            assert got & 0xFF == want, f"op {i}: pop got {got:#x} want {want:#x}"
        elif k < 0.75:
            v = r.choice([0x100, 0x200, 0x300])      # write-1-to-clear of the overflow / underflow flags
            await w.write(M.FLAGS, v)
            m.write(M.FLAGS, v)
        elif k < 0.80:
            v = r.randrange(32)
            await w.write(M.AF_THRESH, v)
            m.write(M.AF_THRESH, v)
        else:
            off = r.choice([M.HEAD, M.LEVEL, M.FLAGS, M.AF_THRESH])
            got = await w.read(off)
            want = m.read(off)
            assert got == want, f"op {i}: read {off} got {got:#x} want {want:#x}"
        if i % 7 == 0:
            await RisingEdge(dut.clk)
    tr.finish()
