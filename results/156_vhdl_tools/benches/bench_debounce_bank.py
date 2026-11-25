"""t1_debounce_bank (entity debounce_bank, DEBOUNCE_CYCLES=6): switches settle to random values; level, edge flags and counters against the golden model."""
import cocotb
from common import Trace, Window, ops, rng, start_clock
from loadmodel import load_model

M = load_model("t1_debounce_bank")
DEB = 6


@cocotb.test()
async def debounce_random(dut):
    await start_clock(dut)
    w = Window(dut)
    w.idle()
    dut.sw_async.value = 0
    tr = Trace("debounce_bank", dut.clk, {"led": dut.led, "rdata": dut.win_rdata})
    await w.reset()
    tr.enabled = True
    m = M.Model()
    r = rng()
    sw = 0
    for i in range(ops()):
        k = r.random()
        if k < 0.45:
            # a bouncing change: toggle a few times inside the debounce time, then settle at a new value
            new = r.randrange(65536)
            for _ in range(r.randrange(1, 3)):
                dut.sw_async.value = r.randrange(65536)
                await w.cycles(r.randrange(1, 3))
            dut.sw_async.value = new
            await w.cycles(DEB + 8)
            m.settle(new)
            sw = new
        elif k < 0.55:
            v = r.randrange(65536)
            await w.write(M.RISE_EN, v)
            m.write(M.RISE_EN, v)
        elif k < 0.65:
            v = r.randrange(65536)
            await w.write(M.FALL_EN, v)
            m.write(M.FALL_EN, v)
        elif k < 0.72:
            v = r.randrange(65536)
            await w.write(M.EDGES, v)
            m.write(M.EDGES, v)
        elif k < 0.76:
            g = r.randrange(4)
            await w.write(M.COUNT0 + g, 0)
            m.write(M.COUNT0 + g, 0)
        else:
            off = r.choice([M.LEVEL, M.EDGES, M.RISE_EN, M.FALL_EN] + [M.COUNT0 + g for g in range(4)])
            got = await w.read(off)
            want = m.read(off)
            assert got == want, f"op {i}: read {off} got {got:#x} want {want:#x} (switches settled at {sw:#06x})"
    tr.finish()
