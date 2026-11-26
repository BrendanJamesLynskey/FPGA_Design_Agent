"""Shared cocotb helpers and the golden models of the three probe tasks (brief 171). The same bench runs the SV candidate and the
Hardcaml candidate's generated Verilog: random stimulus for 3000 clocks with mid-run resets, outputs compared after every clock edge."""
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


class Gray:
    def __init__(s): s.c = 0
    def reset(s): s.c = 0
    def step(s, i):
        if i["step"]: s.c = (s.c + (-1 if i["dir"] else 1)) & 1023
    def out(s): return {"gray": s.c ^ (s.c >> 1)}
    def stim(s, r): return {"step": r.random() < 0.6, "dir": r.random() < 0.5}


class Bcd:
    def __init__(s): s.c = 0; s.w = 0
    def reset(s): s.c = 0; s.w = 0
    def step(s, i):
        d = [1, 2, 5, 10][i["step_sel"]]
        if i["up"] and not i["down"]:
            s.c += d
            if s.c > 9999: s.c -= 10000; s.w = (s.w + 1) & 255
        elif i["down"] and not i["up"]:
            s.c -= d
            if s.c < 0: s.c += 10000; s.w = (s.w + 1) & 255
    def out(s):
        v = 0
        for k in range(4): v |= ((s.c // 10 ** k) % 10) << (4 * k)
        return {"bcd": v, "wraps": s.w}
    def stim(s, r): return {"up": r.random() < 0.45, "down": r.random() < 0.45, "step_sel": r.randrange(4)}


class Fifo:
    def __init__(s): s.q = []; s.o = 0; s.u = 0
    def reset(s): s.q = []; s.o = 0; s.u = 0
    def step(s, i):
        was_full, was_empty = len(s.q) == 16, len(s.q) == 0
        if i["clear_err"]: s.o = 0; s.u = 0
        if i["pop"]:
            if was_empty: s.u = 1
            else: s.q.pop(0)
        if i["push"]:
            if was_full: s.o = 1
            else: s.q.append(i["push_data"])
    def out(s):
        return {"head": s.q[0] if s.q else 0, "count": len(s.q), "empty": int(not s.q), "full": int(len(s.q) == 16),
                "overflow_err": s.o, "underflow_err": s.u}
    def stim(s, r):
        mode = r.random()
        pp = 0.7 if mode < 0.3 else (0.3 if mode < 0.6 else 0.5)
        return {"push": r.random() < pp, "push_data": r.randrange(256), "pop": r.random() < (1 - pp + 0.1), "clear_err": r.random() < 0.03}


MODELS = {"gray_step": Gray, "bcd_updown": Bcd, "fifo16": Fifo}


async def run(dut, name):
    m = MODELS[name]()
    r = random.Random(int(os.environ.get("PROBE_SEED", "7")))
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    sigs = list(m.stim(r).keys())

    async def drive(i):
        for k, v in i.items(): getattr(dut, k).value = int(v)

    n_bad, checked = 0, 0
    await drive({k: 0 for k in sigs})
    for clk in range(3000):
        rst = clk < 3 or r.random() < 0.004
        dut.rst_n.value = 0 if rst else 1
        i = m.stim(r)
        await drive(i)
        await RisingEdge(dut.clk)
        if rst: m.reset()
        else: m.step(i)
        await Timer(1, unit="ns")
        for k, v in m.out().items():
            got = getattr(dut, k).value
            checked += 1
            if not got.is_resolvable or int(got) != v:
                n_bad += 1
                if n_bad <= 3: dut._log.error(f"clock {clk}: {k} = {got}, expected {v}")
    assert n_bad == 0, f"{n_bad} mismatches in {checked} checks"
