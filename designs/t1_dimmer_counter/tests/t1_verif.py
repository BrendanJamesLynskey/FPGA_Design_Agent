"""T1's V2 tests (brief 04f): directed closure, simultaneous presses, and constrained-random operations
(cocotb-coverage `crv`), all against the blind golden model through t1_cocotb.Env. Run together with t1_cocotb
by test_t1_verif.py, once per seed. The names here are the ones verif/testplan.yaml traces to.
"""

from __future__ import annotations

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly
from cocotb_coverage.crv import Randomized

from designs.t1_dimmer_counter import model as m
from designs.t1_dimmer_counter.tests import t1_cov
from designs.t1_dimmer_counter.tests.t1_cocotb import BUTTONS, Env


async def press_together(e: Env, buttons: tuple[str, ...]) -> None:
    """Hold several buttons for the same clean interval: their debounced presses land on one clock."""
    for b in buttons:
        getattr(e.dut, b).value = 1
    await ClockCycles(e.dut.CLK100MHZ, e.n + 4)
    for b in buttons:
        getattr(e.dut, b).value = 0
    await ClockCycles(e.dut.CLK100MHZ, e.n + 4)
    kw = {dict(zip(BUTTONS, ("up", "down", "clear")))[b]: True for b in buttons}
    e.t1.press(**kw)
    for b in buttons:
        t1_cov.sample_trace(dict(zip(BUTTONS, t1_cov.BTN))[b], "clean")


# req: REQ-01
@cocotb.test()
async def simultaneous_presses_priority(dut):
    """spec behaviour.counter: presses on one clock act by priority clear > up > down; each still counts."""
    e = Env(dut)
    await e.start()
    await e.write(m.COUNT, 100)
    for combo in (("BTNU", "BTND"), ("BTNU", "BTNC"), ("BTND", "BTNC"), ("BTNU", "BTND", "BTNC")):
        await press_together(e, combo)
        await e.read(m.COUNT)
        await e.read(m.PRESSES)
        await e.write(m.COUNT, 100)


# req: REQ-02
@cocotb.test()
async def short_glitches_are_ignored(dut):
    """spec behaviour.debounce: a difference shorter than DEBOUNCE_CYCLES is ignored, on every button."""
    e = Env(dut)
    await e.start()
    for b in BUTTONS:
        await e.drive_trace(b, [1] * (e.n - 1) + [0] * (e.n + 4))
        await e.drive_trace(b, ([1, 0] * 3) + [1] * (e.n // 2) + [0] * (e.n + 4))
    assert await e.read(m.PRESSES) == 0 and await e.read(m.COUNT) == 0


# req: REQ-01, REQ-04, REQ-05
@cocotb.test()
async def directed_closure_sweep(dut):
    """Every operation at count 0, 0xFFFF and a middle value; every duty class from both sources; every
    register read and written; every glyph on the display (the bins of verif/testplan.yaml)."""
    e = Env(dut)
    await e.start()
    for count in (0x0000, 0xFFFF, 0x1234):
        for b in BUTTONS:
            await e.write(m.COUNT, count)
            await e.clean_press(b)
            await e.read(m.COUNT)
    for duty in (0x00, 0x20, 0x80, 0xE0, 0xFF):
        await e.write(m.DUTY, duty)
    await e.write(m.CTRL, m.CTRL_DUTY_SRC | m.CTRL_DISPLAY_EN)
    for sw in (0x0000, 0x0020, 0x0080, 0x00E0, 0x00FF):
        await e.set_switches(sw)
    await e.write(m.CTRL, 0)
    await e.write(m.CTRL, m.CTRL_DISPLAY_EN)
    for off in (m.COUNT, m.DUTY, m.CTRL, m.INPUTS, m.PRESSES, 0x05, 0x40, 0x7F):
        await e.read(off)
        await e.write(off, 0x5A5A5A5A)
    for count in (0x3210, 0x7654, 0xBA98, 0xFEDC):
        await e.write(m.COUNT, count)


# req: REQ-05
@cocotb.test()
async def reset_state_of_outputs(dut):
    """spec reset: every register returns to its reset value. While reset is held the display is dark; right
    after it is released the debounced button levels are 0 (found by the first mutation run, 04f)."""
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, "ns").start())
    for b in BUTTONS:
        getattr(dut, b).value = 0
    dut.SW.value = 0
    dut.CPU_RESETN.value = 0
    await ClockCycles(dut.CLK100MHZ, 6)
    await ReadOnly()
    assert int(dut.AN.value) == 0xFF, f"AN={int(dut.AN.value):08b} while reset is held"
    await ClockCycles(dut.CLK100MHZ, 1)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 4)
    await ReadOnly()
    d = dut.u_dut
    assert (int(d.lv_up.value), int(d.lv_down.value), int(d.lv_clear.value)) == (0, 0, 0)


class Op(Randomized):
    """One random operation. The constraints keep every draw legal and weight nothing by hand."""

    def __init__(self) -> None:
        super().__init__()
        self.kind = "read"
        self.button = "BTNU"
        self.reg = 0
        self.vclass = "rand"
        self.add_rand("kind", ["press", "bounce", "write", "switch", "read"])
        self.add_rand("button", list(BUTTONS))
        self.add_rand("reg", [m.COUNT, m.DUTY, m.CTRL, m.INPUTS, m.PRESSES, 0x05, 0x7F])
        self.add_rand("vclass", ["zero", "one", "max", "rand"])
        # window writes to RO registers and unmapped offsets are legal (ignored) but we keep them rare:
        self.add_constraint(lambda kind, reg: kind != "write" or reg in (m.COUNT, m.DUTY, m.CTRL) or reg == 0x05)
        # an all-ones value written to CTRL only matters in its low two bits; keep CTRL values distinct
        self.add_constraint(lambda reg, vclass: reg != m.CTRL or vclass != "one")


def value_of(op: Op, rng: random.Random) -> int:
    return {"zero": 0, "one": 1, "max": 0xFFFFFFFF, "rand": rng.getrandbits(32)}[op.vclass]


async def run_ops(e: Env, n: int, rng: random.Random, bias=None) -> None:
    op = Op()
    for _ in range(n):
        op.randomize_with(bias) if bias else op.randomize()
        if op.kind == "press":
            await e.clean_press(op.button)
        elif op.kind == "bounce":
            trace: list[int] = []
            for _ in range(rng.randint(1, 6)):
                trace += [rng.randint(0, 1)] * rng.randint(1, e.n + 4)
            trace += [0] * (e.n + 4)
            await e.drive_trace(op.button, trace)
            for _ in range(m.presses_in(trace, e.n)):
                e.t1.press(**{dict(zip(BUTTONS, ("up", "down", "clear")))[op.button]: True})
        elif op.kind == "write":
            await e.write(op.reg, value_of(op, rng))
        elif op.kind == "switch":
            await e.set_switches(rng.getrandbits(16))
        else:
            await e.read(op.reg)


# req: REQ-01, REQ-05, REQ-09
@cocotb.test()
async def constrained_random_operations(dut):
    """Constrained-random operation mix (cocotb-coverage crv), then a presses-and-bounces-heavy second phase;
    every register value the RTL returns is compared with the model by Env.access."""
    e = Env(dut)
    await e.start()
    rng = random.Random(int(cocotb.RANDOM_SEED))
    random.seed(int(cocotb.RANDOM_SEED))          # crv draws from the global random module
    await run_ops(e, 50, rng)
    await run_ops(e, 30, rng, bias=lambda kind: kind in ("press", "bounce"))
    for off in (m.COUNT, m.DUTY, m.CTRL, m.INPUTS, m.PRESSES):
        await e.read(off)


# structural: writes the functional-coverage database for the gates; it checks nothing itself
@cocotb.test()
async def zz_dump_coverage(dut):
    """Last test of a run: write the functional-coverage database for flow/verif_gates.py."""
    t1_cov.dump()
