"""cocotb bench: ml_gate_pre against a behavioural expectation, with the class arriving before, with and after the
rule's decision (the integration only has it early or in the same clock, so the hold path is exercised here).

A message: inst_v at clock 0 of its 16-clock slot; trk_v at clock 1 when tracked; the class (cls_v, one clock) at dc in
2..9; the rule's decision (fire_v, order and side) at df in 4..8. With the gate enabled and the message tracked the
decision leaves at max(df, dc) with its order kept only if the class agrees with its side (buy needs 2, sell needs 0);
otherwise it leaves at df unchanged. Vetoes = orders kept by the rule and refused by the class. Also: a class of an
earlier message is never used for a later one (the class is cleared by the next inst_v).
"""
from __future__ import annotations

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge


@cocotb.test()
async def gate_timing_and_veto(dut):
    cocotb.start_soon(Clock(dut.clk, 2, unit="ns").start())
    rng = random.Random(93)
    dut.rst.value = 1
    for s in ("en", "inst_v", "trk_v", "fire_v", "fire_order", "fire_side", "cls_v", "cls", "fire_rest"):
        getattr(dut, s).value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await FallingEdge(dut.clk)
    exp_veto = errors = checked = delayed = immediate = 0
    n = 3000
    for m in range(n):
        dc, df = rng.randint(2, 9), rng.randint(4, 8)
        tracked, en = rng.random() < 0.7, rng.random() < 0.85
        order, side, c, rest = rng.random() < 0.7, rng.randint(0, 1), rng.randint(0, 2), rng.randint(0, 255)
        agree = (c == 0) if side else (c == 2)
        t_out = max(df, dc) if (tracked and en) else df
        keep = (order and agree) if (tracked and en) else order
        if tracked and en and order and not agree:
            exp_veto += 1
        dut.en.value = int(en)
        for k in range(16):
            dut.inst_v.value = int(k == 0)
            dut.trk_v.value = int(k == 1 and tracked)
            dut.cls_v.value = int(tracked and k == dc)
            dut.cls.value = c if (tracked and k == dc) else rng.randint(0, 2)
            dut.fire_v.value = int(k == df)
            dut.fire_order.value = int(order)
            dut.fire_side.value = side
            dut.fire_rest.value = rest
            await ReadOnly()
            v = int(dut.o_fire_v.value)
            if k == t_out:
                checked += 1
                ok = v == 1 and int(dut.o_fire_order.value) == int(keep) and int(dut.o_fire_side.value) == side \
                    and int(dut.o_fire_rest.value) == rest
                errors += 0 if ok else 1
                if tracked and en:
                    delayed += int(dc > df)
                    immediate += int(dc <= df)
            else:
                errors += 0 if v == 0 else 1
            await FallingEdge(dut.clk)
    await ReadOnly()
    dut._log.info(f"decisions {checked}, held {delayed}, immediate {immediate}, expected vetoes {exp_veto}")
    assert errors == 0, errors
    assert int(dut.vetoes.value) == exp_veto, (int(dut.vetoes.value), exp_veto)
    assert delayed > 100 and immediate > 100
