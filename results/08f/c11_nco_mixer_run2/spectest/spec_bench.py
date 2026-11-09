import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

import spec_ref
from shell.tests.uart_bfm import UartBfm
from shell.host import protocol as p

PARAMS = {"CLKS_PER_BIT": 8, "TIMEOUT_CYCLES": 100000, "BUILD_STAMP": 0}
SEEDS = (1,)

W = 0x80  # window base: design register offset + 0x80
MASK, GO, STATUS, NOUT, VMASK, FW = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05
SAMP, OUT = 0x10, 0x20


async def setup(dut):
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, units="ns").start())
    dut.CPU_RESETN.value = 0
    bfm = UartBfm(dut.CLK100MHZ, dut.UART_TXD_IN, dut.UART_RXD_OUT, PARAMS["CLKS_PER_BIT"])
    await ClockCycles(dut.CLK100MHZ, 20)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 20)
    return bfm


async def rd(bfm, off):
    r = p.decode_response(await bfm.transact(p.encode_request(p.CMD_READ, W + off)))
    assert r.status == p.ST_OK, f"read of window offset 0x{off:02X} gave status {r.status_name}"
    return r.data


async def wr(bfm, off, val):
    r = p.decode_response(await bfm.transact(p.encode_request(p.CMD_WRITE, W + off, val)))
    assert r.status == p.ST_OK, f"write of window offset 0x{off:02X} gave status {r.status_name}"


def make_mask(rng, n):
    pos = rng.sample(range(31), n)  # avoid clock 31 (result would fall at clock 32)
    m = 0
    for b in pos:
        m |= 1 << b
    return m


async def run_burst(bfm, model, fw, samples, mask, tag):
    await wr(bfm, FW, fw)
    for i, x in enumerate(samples):
        await wr(bfm, SAMP + i, x & 0xFFF)
    await wr(bfm, MASK, mask)
    await wr(bfm, GO, 1)
    done = 0
    for _ in range(5):
        done = await rd(bfm, STATUS)
        if done & 1:
            break
    assert done == 1, f"{tag}: STATUS expected DONE=1 (other bits 0) after burst, read 0x{done:X}"
    exp, nexp, vexp = spec_ref.burst(model, fw, samples, mask)
    n = await rd(bfm, NOUT)
    assert n == nexp, f"{tag}: NOUT expected {nexp} results, read {n}"
    v = await rd(bfm, VMASK)
    assert v == vexp, f"{tag}: VMASK expected 0x{vexp:08X} (bit n = result in clock n+1), read 0x{v:08X}"
    for i in range(nexp):
        o = await rd(bfm, OUT + i)
        assert o == exp[i], (f"{tag}: OUT{i} expected 0x{exp[i]:08X} "
                             f"(i_out[11:0], q_out[27:16]), read 0x{o:08X}; fw=0x{fw:04X} x={samples[i]}")
    if nexp < 16:
        o = await rd(bfm, OUT + nexp)
        assert o == 0, f"{tag}: OUT{nexp} beyond NOUT expected 0, read 0x{o:08X}"


@cocotb.test()
async def registers_reset_and_widths(dut):
    bfm = await setup(dut)
    r = p.decode_response(await bfm.transact(p.encode_request(p.CMD_READ, 0x00)))
    assert r.data == 0x4E434F4D, f"DESIGN_ID expected 'NCOM' 0x4E434F4D, read 0x{r.data:08X}"
    for off in (MASK, STATUS, NOUT, VMASK, FW, SAMP, OUT):
        v = await rd(bfm, off)
        assert v == 0, f"reset value of offset 0x{off:02X} expected 0, read 0x{v:X}"
    await wr(bfm, FW, 0xFFFF1234)
    v = await rd(bfm, FW)
    assert v == 0x1234, f"FW expected [15:0] only (0x1234), read 0x{v:08X}"
    await wr(bfm, SAMP + 3, 0xFFFFF801)
    v = await rd(bfm, SAMP + 3)
    assert v == 0x801, f"SAMP3 expected [11:0] only (0x801), read 0x{v:08X}"
    await wr(bfm, MASK, 0xA5C3_0F01)
    v = await rd(bfm, MASK)
    assert v == 0xA5C30F01, f"MASK expected 32-bit readback 0xA5C30F01, read 0x{v:08X}"
    await wr(bfm, NOUT, 0x3F)
    v = await rd(bfm, NOUT)
    assert v == 0, f"write to RO NOUT must be ignored, read 0x{v:X}"


@cocotb.test()
async def tone_burst_matches_model(dut):
    bfm = await setup(dut)
    model = spec_ref.Nco()
    # a tone at the oscillator frequency (fw/2^16 of the sample rate), contiguous samples
    import math
    fw = 0x1000
    samples = [int(round(1500 * math.cos(2 * math.pi * n / 16))) for n in range(16)]
    await run_burst(bfm, model, fw, samples, 0xFFFF, "tone")


@cocotb.test()
async def gaps_hold_phase_and_phase_persists_across_bursts(dut):
    bfm = await setup(dut)
    model = spec_ref.Nco()
    rng = random.Random(7)
    for b, fw in enumerate((0x0B35, 0x6001, 0x0B35)):
        ns = 5 + 3 * b
        samples = [rng.randint(-2048, 2047) for _ in range(ns)]
        await run_burst(bfm, model, fw, samples, make_mask(rng, ns), f"burst{b}")


@cocotb.test()
async def full_scale_and_rounding(dut):
    bfm = await setup(dut)
    model = spec_ref.Nco()
    samples = [-2048, 2047, -2048, 2047, -1, 1, 0, -2048, 2047, -1, 1, -2048, 2047, -2047, 3, -3]
    # fw odd, large: touches many table indices incl. sine/cosine extremes
    await run_burst(bfm, model, 0x4001, samples, 0x7FFF8, "fullscale-a")
    await run_burst(bfm, model, 0xC0FF, samples[::-1], 0x5555_5555 & 0x7FFF_FFFF & 0x15555555 | 0x1, "fullscale-b")


@cocotb.test()
async def reset_clears_phase_and_loaded_values(dut):
    bfm = await setup(dut)
    model = spec_ref.Nco()
    rng = random.Random(3)
    samples = [rng.randint(-2048, 2047) for _ in range(8)]
    await run_burst(bfm, model, 0x2345, samples, 0xFF, "pre-reset")
    # reset: phase back to 0 and loaded values cleared
    dut.CPU_RESETN.value = 0
    await ClockCycles(dut.CLK100MHZ, 10)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 20)
    model.reset()
    v = await rd(bfm, SAMP)
    assert v == 0, f"SAMP0 expected 0 after CPU_RESETN, read 0x{v:X}"
    samples = [rng.randint(-2048, 2047) for _ in range(8)]
    await run_burst(bfm, model, 0x2345, samples, 0x1FE, "post-reset")
