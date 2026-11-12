"""Adversarial bench for ip_lib/fir, written by an independent reviewer of the variants work: concurrent coefficient and sample drivers, beats interleaved with
samples, partial loads, reloads with results still in flight, output back-pressure and reset mid-stream. The expected
values come from an event log recorded by a monitor (handshakes seen at each clock edge) and a plain model."""
import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


def extremes(w, rng):
    lo, hi = -(1 << (w - 1)), (1 << (w - 1)) - 1
    r = rng.random()
    if r < 0.15: return lo
    if r < 0.30: return hi
    if r < 0.35: return -1
    if r < 0.40: return 0
    return rng.randint(lo, hi)


@cocotb.test()
async def adv(dut):
    taps, dw, cw = int(dut.TAPS.value), int(dut.DATA_W.value), int(dut.COEF_W.value)
    mode = os.environ.get("ADV_MODE", "mix")
    seed = int(os.environ.get("ADV_SEED", "1"))
    rng = random.Random(seed)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for s in (dut.c_valid, dut.c_data, dut.c_last, dut.s_valid, dut.s_data, dut.m_ready):
        s.value = 0
    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0

    events = []          # ("c", data, last) / ("s", data) / ("m", data) / ("r",)
    errors = []
    stop = {"v": False}

    async def monitor():
        while not stop["v"]:
            await RisingEdge(dut.clk)
            if dut.rst.value == 1:
                events.append(("r",)); continue
            c = dut.c_valid.value == 1 and dut.c_ready.value == 1
            s = dut.s_valid.value == 1 and dut.s_ready.value == 1
            if c and s:
                errors.append("c and s in one clock")
            if c: events.append(("c", dut.c_data.value.to_signed(), int(dut.c_last.value)))
            if s: events.append(("s", dut.s_data.value.to_signed()))
            if dut.m_valid.value == 1 and dut.m_ready.value == 1:
                events.append(("m", dut.m_data.value.to_signed()))

    async def cdrv(n_loads):
        for _ in range(n_loads):
            await Timer(rng.randint(1, 60) * 10, unit="ns")
            await RisingEdge(dut.clk)
            ln = taps if rng.random() < 0.6 else rng.randint(1, taps)     # partial loads too
            for i in range(ln):
                dut.c_valid.value = 1
                dut.c_data.value = extremes(cw, rng)
                dut.c_last.value = int(i == ln - 1 and (ln < taps or rng.random() < 0.7))
                while True:
                    await RisingEdge(dut.clk)
                    if dut.c_ready.value == 1 and dut.rst.value == 0:
                        break
                if mode == "mix" and rng.random() < 0.3:          # drop c_valid between beats: samples may slip in
                    dut.c_valid.value = 0
                    for _ in range(rng.randint(1, 3 * taps)):
                        await RisingEdge(dut.clk)
            dut.c_valid.value = 0
            dut.c_last.value = 0

    async def sdrv(n):
        for _ in range(n):
            while rng.random() < 0.25:
                dut.s_valid.value = 0
                await RisingEdge(dut.clk)
            dut.s_valid.value = 1
            dut.s_data.value = extremes(dw, rng)
            while True:
                await RisingEdge(dut.clk)
                if dut.s_ready.value == 1 and dut.rst.value == 0:
                    break
        dut.s_valid.value = 0

    async def mdrv():
        while not stop["v"]:
            dut.m_ready.value = int(rng.random() >= 0.35)
            await RisingEdge(dut.clk)

    async def rdrv(k):
        for _ in range(k):
            await Timer(rng.randint(200, 900) * 10, unit="ns")
            await RisingEdge(dut.clk)
            dut.rst.value = 1
            for _ in range(rng.randint(1, 3)):
                await RisingEdge(dut.clk)
            dut.rst.value = 0

    cocotb.start_soon(monitor())
    cocotb.start_soon(mdrv())
    nsamp = int(os.environ.get("ADV_N", "400"))
    tc = cocotb.start_soon(cdrv(int(os.environ.get("ADV_LOADS", "6"))))
    ts = cocotb.start_soon(sdrv(nsamp))
    if mode == "reset":
        cocotb.start_soon(rdrv(3))
    await ts
    await tc
    for _ in range(40 * taps + 400):
        await RisingEdge(dut.clk)
    stop["v"] = True
    await RisingEdge(dut.clk)

    # replay the event log against the model
    h, ck, hist, pend = [0] * taps, 0, [], []
    nm = nres = 0
    for ev in events:
        if ev[0] == "r":
            h, ck, hist, pend = [0] * taps, 0, [], []
        elif ev[0] == "c":
            h[ck] = ev[1]
            ck = 0 if (ev[2] or ck == taps - 1) else ck + 1
        elif ev[0] == "s":
            hist.append(ev[1])
            pend.append(sum(h[k] * hist[-1 - k] for k in range(min(taps, len(hist)))))
        else:
            nm += 1
            if not pend:
                errors.append(f"output {ev[1]} with nothing pending"); continue
            w = pend.pop(0)
            nres += 1
            if ev[1] != w:
                errors.append(f"output #{nm}: got {ev[1]}, want {w}")
    if pend:
        errors.append(f"{len(pend)} results never came out")
    kinds = {k: sum(1 for e in events if e[0] == k) for k in "csmr"}
    dut._log.info(f"events {kinds}; {nres} outputs checked; {len(errors)} errors")
    assert not errors, errors[:5]
