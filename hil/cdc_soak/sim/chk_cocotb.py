"""cocotb tests of the rig's checkers and record (tb_chk): an injected error is counted, the counters saturate, the
record chain rotates back intact, relocks are separate from errors, and lock-ups are counted by the watchdog."""

from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge


def prbs16_next(w: int) -> int:
    fb = ((w >> 15) ^ (w >> 13) ^ (w >> 12) ^ (w >> 10)) & 1
    return ((w << 1) & 0xFFFF) | fb


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for s in ("frz", "sh", "sin", "e_err", "e_ev", "e_lock", "e_relock", "w_valid", "w_arm", "w_hold", "v_ev",
              "h_rqs"):
        getattr(dut, s).value = 0
    dut.w_w.value = 0
    dut.v_ref.value = 0
    dut.c_v.value = 0
    dut.c_raw.value = 0
    dut.h_q.value = 0
    await ClockCycles(dut.clk, 3)
    await FallingEdge(dut.clk)


async def pulse(dut, name, n):
    for _ in range(n):
        getattr(dut, name).value = 1
        await FallingEdge(dut.clk)
        getattr(dut, name).value = 0
        await FallingEdge(dut.clk)


def fields(r: int):
    # {errors 4, events 4, lockups 3, relocks 3, sat 1} = 15 bits
    return {"err": r >> 11, "ev": (r >> 7) & 0xF, "lock": (r >> 4) & 0x7, "relock": (r >> 1) & 0x7, "sat": r & 1}


@cocotb.test()
async def record_counts_and_saturates(dut):
    await setup(dut)
    await pulse(dut, "e_err", 3)
    assert fields(int(dut.u_rec.r.value))["err"] == 3, "an injected error is counted"
    await pulse(dut, "e_err", 17)
    await pulse(dut, "e_lock", 9)
    await pulse(dut, "e_relock", 9)
    await pulse(dut, "e_ev", 20)
    f = fields(int(dut.u_rec.r.value))
    assert f == {"err": 15, "ev": 20 % 16, "lock": 7, "relock": 7, "sat": 1}, f
    # frozen: nothing counts
    dut.frz.value = 1
    await pulse(dut, "e_ev", 3)
    assert fields(int(dut.u_rec.r.value))["ev"] == 4
    # the chain rotates back intact after 15 shifts (sin fed from sout, as in a one-copy chain)
    before = int(dut.u_rec.r.value)
    seen = []
    for _ in range(15):
        await ReadOnly()
        seen.append(int(dut.sout.value))
        await FallingEdge(dut.clk)
        dut.sin.value = seen[-1]
        dut.sh.value = 1
        await FallingEdge(dut.clk)
        dut.sh.value = 0
    assert int(dut.u_rec.r.value) == before
    assert int("".join(map(str, seen)), 2) == before, "the bits come out MSB first"


@cocotb.test()
async def words_relock_error_lockup(dut):
    await setup(dut)
    errs = relocks = locks = 0

    async def send(w):
        nonlocal errs, relocks
        dut.w_w.value = w
        dut.w_valid.value = 1
        await RisingEdge(dut.clk)
        await ReadOnly()
        errs += int(dut.w_err.value)
        relocks += int(dut.w_relock.value)
        await FallingEdge(dut.clk)
        dut.w_valid.value = 0

    w = 0xACE1
    await send(w)                     # power-up: first word is a relock
    for _ in range(10):
        w = prbs16_next(w)
        await send(w)
    assert (errs, relocks) == (0, 1)
    await send(0x1234)                # a corrupted word with no reset: an error
    assert (errs, relocks) == (1, 1)
    dut.w_arm.value = 1               # a reset event arms one relock
    await FallingEdge(dut.clk)
    dut.w_arm.value = 0
    await send(0xBEEF)
    await send(0x0001)                # a second discontinuity after the same reset: an error
    assert (errs, relocks) == (2, 2)
    # no words for 2^6 cycles: a lock-up (and none while held)
    for _ in range(140):
        await RisingEdge(dut.clk)
        await ReadOnly()
        locks += int(dut.w_lock.value)
    assert locks == 2, locks
    await FallingEdge(dut.clk)
    dut.w_hold.value = 1
    for _ in range(140):
        await RisingEdge(dut.clk)
        await ReadOnly()
        locks += int(dut.w_lock.value)
    assert locks == 2


@cocotb.test()
async def events_quiet_point_and_glitch(dut):
    await setup(dut)
    n = 0
    errs = 0

    async def cycle():
        nonlocal errs
        await RisingEdge(dut.clk)
        await ReadOnly()
        errs += int(dut.v_err.value)
        await FallingEdge(dut.clk)

    for i in range(5):                 # matched events: ref follows the destination count
        dut.v_ev.value = 1
        n += 1
        await cycle()
        dut.v_ev.value = 0
        dut.v_ref.value = n
        for _ in range(12):
            await cycle()
    assert errs == 0
    dut.v_ev.value = 1                 # one extra (glitch-free) event that the source never sent
    await cycle()
    dut.v_ev.value = 0
    for _ in range(12):
        await cycle()
    assert errs == 1, "a lost/extra event is one error at the next quiet point"
    for _ in range(12):
        await cycle()
    assert errs == 1, "and is then absorbed"
    dut.v_ev.value = 1                 # two level changes one cycle apart: a glitch
    await cycle()
    dut.v_ev.value = 0
    await cycle()
    dut.v_ev.value = 1
    await cycle()
    dut.v_ev.value = 0
    dut.v_ref.value = n + 2
    for _ in range(12):
        await cycle()
    assert errs >= 2


@cocotb.test()
async def count_and_coherence(dut):
    await setup(dut)
    errs = 0

    def gray(b):
        return b ^ (b >> 1)

    async def cycle(sig):
        nonlocal errs
        await RisingEdge(dut.clk)
        await ReadOnly()
        errs += int(getattr(dut, sig).value)
        await FallingEdge(dut.clk)

    for v in range(1, 30):
        dut.c_v.value = v
        dut.c_raw.value = gray(v)
        await cycle("c_err")
    assert errs == 0
    dut.c_v.value = 40                 # a jump of 11 > MAXSTEP
    dut.c_raw.value = gray(40)
    await cycle("c_err")
    await cycle("c_err")
    assert errs >= 1
    errs = 0
    dut.h_rqs.value = 1
    dut.h_q.value = 0
    await cycle("h_err")
    dut.h_rqs.value = 0
    dut.h_q.value = 0xFFFFFFFF          # coherent release
    await cycle("h_err")
    dut.h_q.value = 0
    await cycle("h_err")
    assert errs == 0
    dut.h_q.value = 0x0000FFFF          # half the flops a cycle late: one error for this release
    for _ in range(5):
        await cycle("h_err")
    assert errs == 1
