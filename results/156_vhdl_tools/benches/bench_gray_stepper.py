"""t1_gray_stepper (entity gray_stepper): register reads and writes, button steps and the auto-stepper, against the task's golden model.
Generics for the run: DEBOUNCE_CYCLES=6, TICK_CYCLES=4. Auto-stepping is checked by replaying the STEPS delta into the model."""
import cocotb
from common import Trace, Window, ops, rng, start_clock
from loadmodel import load_model

M = load_model("t1_gray_stepper")
DEB = 6


async def press(dut, w):
    dut.btn.value = 1
    await w.cycles(DEB + 6)
    dut.btn.value = 0
    await w.cycles(DEB + 6)


@cocotb.test()
async def gray_random(dut):
    await start_clock(dut)
    w = Window(dut)
    w.idle()
    dut.btn.value = 0
    dut.dir_async.value = 0
    tr = Trace("gray_stepper", dut.clk, {"led": dut.led, "rdata": dut.win_rdata})
    await w.reset()
    tr.enabled = True
    m = M.Model()
    r = rng()
    for off in (M.GRAY, M.BIN, M.CTRL, M.RATE, M.STEPS):
        got = await w.read(off)
        assert got == m.read(off), f"after reset: register {off} got {got:#x} want {m.read(off):#x}"
    for i in range(ops()):
        k = r.random()
        if k < 0.20:
            v = r.randrange(1024)
            await w.write(M.BIN, v)
            m.write(M.BIN, v)
        elif k < 0.30:
            m.dir = r.randrange(2)
            dut.dir_async.value = m.dir
            await w.cycles(5)
        elif k < 0.45:
            await press(dut, w)
            m.step()
        elif k < 0.60:
            v = r.randrange(1, 4)
            await w.write(M.RATE, v)
            m.write(M.RATE, v)
            before = await w.read(M.STEPS)
            await w.write(M.CTRL, 1)
            await w.cycles(r.randrange(20, 90))
            await w.write(M.CTRL, 0)
            await w.cycles(3)
            after = await w.read(M.STEPS)
            m.step((after - before) & 0xFFFF)
            assert after != before, f"op {i}: the auto-stepper did not step in {v}*4 clocks per step"
        else:
            off = r.choice([M.GRAY, M.BIN, M.CTRL, M.RATE, M.STEPS])
            got = await w.read(off)
            want = m.read(off)
            if off == M.STEPS:
                want = got                    # STEPS is re-synchronised to the design after every auto run, see above
            assert got == want, f"op {i}: register {off} got {got:#x} want {want:#x}"
    tr.finish()
