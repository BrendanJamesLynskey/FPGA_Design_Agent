"""cocotb benches for the brief-30 library instruments; one test per block, selected by the pytest wrapper
(hil/tests/test_30_ip_rtl.py) through the toplevel. The benches only drive and sample; every expected value comes from
hil/instruments/models.py. A failed assertion fails the run (this is how the seeded faults are caught)."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from hil.instruments import models as m


async def start(dut, name="clk"):
    cocotb.start_soon(Clock(getattr(dut, name), 10, unit="ns").start())
    dut.rst.value = 1
    for _ in range(4):
        await RisingEdge(getattr(dut, name))
    dut.rst.value = 0
    await RisingEdge(getattr(dut, name))


@cocotb.test()
async def freq_duty_counter(dut):
    gate = int(dut.GATE_CLKS.value) if hasattr(dut, "GATE_CLKS") else 2000
    await start(dut)
    for period, high in ((20, 5), (50, 25), (200, 20), (7, 3)):
        dut.sig.value = 0
        n_gates = dut.gates.value.to_unsigned()
        sim_clks, k = 0, 0
        # run until two gates have completed with this stimulus, check the second
        want = n_gates + 2
        while dut.gates.value.to_unsigned() < want:
            dut.sig.value = 1 if (k % period) < high else 0
            k += 1
            await RisingEdge(dut.clk)
            sim_clks += 1
            assert sim_clks < 5 * gate, "gate never ended"
        e, h = dut.edges.value.to_unsigned(), dut.high_clks.value.to_unsigned()
        exp_e = gate / period
        exp_h = gate * high / period
        assert abs(e - exp_e) <= 1.01, f"period {period}: edges {e}, expected about {exp_e}"
        assert abs(h - exp_h) <= high + 1, f"period {period} high {high}: high_clks {h}, expected about {exp_h}"
    dut._log.info("freq_duty_counter ok")


@cocotb.test()
async def frame_crc(dut):
    pix_w = int(dut.PIX_W.value)
    await start(dut)
    rng = random.Random(30)
    dut.frame_start.value = 0; dut.pix_valid.value = 0; dut.pix_data.value = 0; dut.crc_expect.value = 0
    frames = []
    for f in range(4):
        n = rng.randint(40, 90)
        words = [rng.getrandbits(pix_w) for _ in range(n)]
        frames.append(words)
    # a first frame that is only a lead-in (not counted: no previous frame), then four real ones, then a closer
    async def send(words, expect, first_with_start=False):
        dut.crc_expect.value = expect
        dut.frame_start.value = 1
        dut.pix_valid.value = 0
        words = list(words)
        if first_with_start:                      # the first pixel arrives on the frame_start clock itself
            dut.pix_valid.value = 1
            dut.pix_data.value = words.pop(0)
        await RisingEdge(dut.clk)
        dut.frame_start.value = 0
        for w in words:
            dut.pix_valid.value = 1
            dut.pix_data.value = w
            await RisingEdge(dut.clk)
            if rng.random() < 0.3:                      # gaps between pixels (blanking)
                dut.pix_valid.value = 0
                await RisingEdge(dut.clk)
        dut.pix_valid.value = 0
    await send([1, 2, 3], 0)
    exps = [m.frame_crc32(w, pix_w) for w in frames]
    for i, w in enumerate(frames):
        # the CRC of the frame that just ended is compared with crc_expect present at the next frame_start
        await send(w, exps[i - 1] if i else m.frame_crc32([1, 2, 3], pix_w), first_with_start=(i % 2 == 1))
    # the previous frame's expected value must be on crc_expect when the next frame_start arrives
    dut.crc_expect.value = exps[-1]
    dut.frame_start.value = 1
    await RisingEdge(dut.clk)
    dut.frame_start.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    assert dut.frames.value.to_unsigned() == 5, f"frames {dut.frames.value}"
    assert dut.crc_last.value.to_unsigned() == exps[-1], f"crc {int(dut.crc_last.value):08x} != {exps[-1]:08x}"
    assert dut.pix_last.value.to_unsigned() == len(frames[-1])
    assert dut.sum_last.value.to_unsigned() == sum(frames[-1]) & 0xFFFFFFFF
    assert dut.mismatches.value.to_unsigned() == 0, f"mismatches {dut.mismatches.value}"
    # one wrong pixel must change the CRC and be counted as a mismatch. The frame open now is empty (its CRC is 0).
    bad = list(frames[0]); bad[len(bad) // 2] ^= 1
    await send(bad, 0)
    dut.crc_expect.value = exps[0]      # expected = the good frame 0
    dut.frame_start.value = 1
    await RisingEdge(dut.clk)
    dut.frame_start.value = 0
    await RisingEdge(dut.clk); await RisingEdge(dut.clk)
    assert dut.mismatches.value.to_unsigned() == 1, "a one-bit pixel error was not counted as a mismatch"
    assert dut.crc_last.value.to_unsigned() == m.frame_crc32(bad, pix_w)
    dut._log.info("frame_crc ok")


@cocotb.test()
async def dds_awg(dut):
    pw, lw, ow = int(dut.PHASE_W.value), int(dut.LUT_W.value), int(dut.OUT_W.value)
    await start(dut)
    for wave, step, sh in ((0, 0x0300_0000, 0), (0, 0x0123_4567, 2), (1, 0x0200_0000 + 0x123, 0), (2, 0x0155_5555, 1), (3, 0x0400_0001, 0)):
        step &= (1 << pw) - 1
        dut.rst.value = 1
        await RisingEdge(dut.clk)
        dut.rst.value = 0
        dut.step.value = step; dut.wave.value = wave; dut.amp_shift.value = sh; dut.tick.value = 1
        await RisingEdge(dut.clk)
        want = m.dds_stream(200, step, wave, pw, lw, ow, sh)
        got = []
        for _ in range(200):
            await RisingEdge(dut.clk)
            got.append(dut.sample.value.to_signed())
        # sample after tick n is dds_sample(phase before tick n); one clock of lag from the first tick above
        assert got[:199] == want[:199] or got[1:] == want[:199], f"wave {wave}: first mismatch {[ (i,a,b) for i,(a,b) in enumerate(zip(got,want)) if a!=b][:3]}"
    dut._log.info("dds_awg ok")


@cocotb.test()
async def logic_analyser(dut):
    width, aw = int(dut.WIDTH.value), int(dut.ADDR_W.value)
    depth = 1 << aw
    await start(dut)
    dut.win_wr.value = 0; dut.win_rd.value = 0; dut.sample_en.value = 1
    dut.win_addr.value = 0; dut.win_wdata.value = 0
    sig = {"v": 0}

    async def wr(a, d):
        dut.win_addr.value = a; dut.win_wdata.value = d; dut.win_wr.value = 1
        await RisingEdge(dut.clk)
        dut.win_wr.value = 0
        await RisingEdge(dut.clk)

    async def rd(a):
        dut.win_addr.value = a; dut.win_rd.value = 1
        await RisingEdge(dut.clk)
        dut.win_rd.value = 0
        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        return dut.win_rdata.value.to_unsigned()

    async def counter_task():
        while True:
            dut.sample.value = sig["v"] & ((1 << width) - 1)
            sig["v"] += 1
            await RisingEdge(dut.clk)
    cocotb.start_soon(counter_task())
    assert await rd(5) == depth
    for pre, trig_val in ((0, 300), (7, 211), (depth // 2, 1000)):
        await wr(2, (1 << width) - 1); await wr(3, trig_val & ((1 << width) - 1)); await wr(4, pre)
        # restart the counter below the trigger value so the trigger has room to fill the pre-trigger depth
        sig["v"] = (trig_val - pre - 20) & ((1 << width) - 1)
        await wr(0, 1)
        for _ in range(depth + 3 * pre + 400):
            await RisingEdge(dut.clk)
            if (await rd(1)) & 4:
                break
        st = await rd(1)
        assert st & 4, f"capture never completed (status {st:#x})"
        for k in (0, pre, pre + 1, depth - 1):
            await wr(6, k)
            v = await rd(7)
            exp = (trig_val - pre + k) & ((1 << width) - 1)
            assert v == exp, f"pre {pre}: sample {k} is {v}, expected {exp}"
    # edge mode: rising edge of bit 3 of the counter
    await wr(2, 0x8); await wr(4, 4); await wr(0, 0b11)
    sig["v"] = 9                                   # bit 3 is high: the first edge after arming is a falling one
    for _ in range(depth + 200):
        await RisingEdge(dut.clk)
        if (await rd(1)) & 4:
            break
    await wr(6, 4)
    v = await rd(7)
    assert (v & 8) and ((v - 1) & 8) == 0 or v == 8, f"edge trigger sample {v}"
    dut._log.info("logic_analyser ok")


@cocotb.test()
async def adc_histogram(dut):
    sw, bw, cw = int(dut.SAMP_W.value), int(dut.BIN_W.value), int(dut.CNT_W.value)
    # inputs driven before reset ends (the bin RAM's write enable is now one combinational term, so a
    # `clear` still undriven in the first clock after reset leaves bin 0 unknown in simulation)
    dut.clear.value = 0; dut.s_valid.value = 0; dut.s_data.value = 0; dut.rd_bin.value = 0
    await start(dut)
    for _ in range((1 << bw) + 4):
        await RisingEdge(dut.clk)
    assert dut.busy.value == 0
    rng = random.Random(7)
    samples = [rng.getrandbits(sw) for _ in range(3000)] + [5 << (sw - bw)] * 40     # random plus a run on one bin
    for s in samples:
        dut.s_valid.value = 1; dut.s_data.value = s
        await RisingEdge(dut.clk)
        if rng.random() < 0.2:
            dut.s_valid.value = 0
            await RisingEdge(dut.clk)
    dut.s_valid.value = 0
    for _ in range(6):
        await RisingEdge(dut.clk)
    want = m.histogram(samples, sw, bw, cw)
    got = []
    for b in range(1 << bw):
        dut.rd_bin.value = b
        await RisingEdge(dut.clk); await RisingEdge(dut.clk)
        got.append(dut.rd_count.value.to_unsigned())
    assert got == want, f"bins differ at {[i for i in range(len(want)) if got[i] != want[i]][:5]}"
    assert dut.total.value.to_unsigned() == len(samples)
    assert dut.min_code.value.to_unsigned() == min(samples) and dut.max_code.value.to_unsigned() == max(samples)
    dut._log.info("adc_histogram ok")
