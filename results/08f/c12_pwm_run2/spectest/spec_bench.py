import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from pathlib import Path
import spec_ref as R
from shell.tests.uart_bfm import UartBfm
from shell.host import protocol as p

PARAMS = {"CLKS_PER_BIT": 16, "TIMEOUT_CYCLES": 2000, "BUILD_STAMP": 0}
SEEDS = (1,)

SAMPLE, GAIN, SOUT = 0x80, 0x81, 0x82


async def setup(dut):
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, unit="ns").start())
    dut.CPU_RESETN.value = 0
    dut.UART_TXD_IN.value = 1
    await ClockCycles(dut.CLK100MHZ, 10)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 5)
    return UartBfm(dut.CLK100MHZ, dut.UART_TXD_IN, dut.UART_RXD_OUT, PARAMS["CLKS_PER_BIT"])


async def rd(bfm, addr):
    r = p.decode_response(await bfm.transact(p.encode_request(p.CMD_READ, addr)))
    assert r.status == p.ST_OK, f"read of 0x{addr:02X} gave status {r.status_name}"
    return r.data


async def wr(bfm, addr, v):
    r = p.decode_response(await bfm.transact(p.encode_request(p.CMD_WRITE, addr, v)))
    assert r.status == p.ST_OK, f"write of 0x{addr:02X} gave status {r.status_name}"


async def measure_lows(dut, periods=2):
    """Low clocks in each of `periods` consecutive 1024-clock windows (any aligned window holds one full period)."""
    res = []
    seen_high = False
    for _ in range(periods):
        n = 0
        for _ in range(R.PERIOD):
            await RisingEdge(dut.CLK100MHZ)
            s = str(dut.AUD_PWM.value).upper()
            if s == "0":
                n += 1
            if s == "1":
                seen_high = True
        res.append(n)
    assert not seen_high, "AUD_PWM was driven high; the pin must only be pulled low or released"
    return res


async def check_pwm(dut, sample, gain):
    await ClockCycles(dut.CLK100MHZ, 2 * R.PERIOD + 8)  # duty updated once per period
    got = await measure_lows(dut)
    exp = R.low_clocks(sample, gain)
    assert got == [exp, exp], (
        f"sample={R.to_signed16(sample)} gain={gain}: expected pin low {exp} clocks "
        f"(1024 - duty) per period, got {got}")


@cocotb.test()
async def reset_defaults_and_id(dut):
    bfm = await setup(dut)
    assert await rd(bfm, 0x00) == R.ID_PWMA, "DESIGN_ID expected 'PWMA'"
    assert await rd(bfm, SAMPLE) == 0, "SAMPLE resets to 0"
    assert await rd(bfm, GAIN) == 0, "GAIN reads 0 always"
    assert await rd(bfm, SOUT) == 0, "SOUT resets to 0"
    assert str(dut.AUD_SD.value) == "1", "AUD_SD (amplifier enable) must be always high"
    await wr(bfm, SAMPLE, 10000)
    exp = R.sample_out(10000, R.GAIN_RESET)
    assert await rd(bfm, SOUT) == exp, f"default gain 2068: sample_out expected {exp}"
    await check_pwm(dut, 10000, R.GAIN_RESET)
    await check_pwm_silence(dut)


async def check_pwm_silence(dut):
    assert str(dut.AUD_SD.value) == "1", "AUD_SD must stay high"


@cocotb.test()
async def gain_write_clamp_and_sample_out(dut):
    bfm = await setup(dut)
    samples = [32767, -32768, 12345, -1, -12345]
    for w in (65535, 4000, 8192, 8193, 0):
        await wr(bfm, GAIN, w)
        g = R.clamp_gain(w)
        assert await rd(bfm, GAIN) == 0, "GAIN cannot be read back and reads 0"
        for s in samples:
            await wr(bfm, SAMPLE, s & 0xFFFF)
            exp = R.sample_out(s, g) & 0xFFFF
            got = await rd(bfm, SOUT)
            assert got == exp, (f"gain write {w} (stored {g}), sample {s}: sample_out expected "
                                f"0x{exp:04X} (floor(sample*gain/2^15), 16-bit two's complement), got 0x{got:04X}")


@cocotb.test()
async def sample_readback_twos_complement(dut):
    bfm = await setup(dut)
    for s in (0, 1, 32767, 0x8000, 0xFFFF, 0x1234):
        await wr(bfm, SAMPLE, s)
        got = await rd(bfm, SAMPLE)
        assert got == s, f"SAMPLE written 0x{s:04X}: expected same back with [31:16]=0, got 0x{got:08X}"


@cocotb.test()
async def pwm_low_clocks_per_period(dut):
    bfm = await setup(dut)
    await wr(bfm, GAIN, 65535)  # clamped to 8192
    g = 8192
    for s in (0, 32767, -32768, -1, 508, 512, -512, -516, 20000):
        await wr(bfm, SAMPLE, s & 0xFFFF)
        await check_pwm(dut, s, g)


@cocotb.test()
async def pwm_at_default_gain_and_floor(dut):
    bfm = await setup(dut)
    for s in (-1, -32768, 32767):
        await wr(bfm, SAMPLE, s & 0xFFFF)
        await check_pwm(dut, s, R.GAIN_RESET)


@cocotb.test()
async def reset_after_write_restores_defaults(dut):
    bfm = await setup(dut)
    await wr(bfm, GAIN, 8192)
    await wr(bfm, SAMPLE, 30000)
    assert await rd(bfm, SOUT) == R.sample_out(30000, 8192), "gain 8192 should apply before reset"
    dut.CPU_RESETN.value = 0
    await ClockCycles(dut.CLK100MHZ, 10)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 5)
    assert await rd(bfm, SAMPLE) == 0, "reset clears the sample"
    assert await rd(bfm, SOUT) == 0, "sample_out is 0 after reset"
    await wr(bfm, SAMPLE, 10000)
    exp = R.sample_out(10000, R.GAIN_RESET)
    assert await rd(bfm, SOUT) == exp, f"reset restores gain 2068: expected sample_out {exp}"
    assert str(dut.AUD_SD.value) == "1", "AUD_SD high after reset"


@cocotb.test()
async def unmapped_and_ro_writes_ignored(dut):
    bfm = await setup(dut)
    await wr(bfm, SAMPLE, 1000)
    exp = await rd(bfm, SOUT)
    r = p.decode_response(await bfm.transact(p.encode_request(p.CMD_WRITE, SOUT, 0x1234)))
    assert r.status == p.ST_OK, "window writes are never an error from the shell"
    assert await rd(bfm, SOUT) == exp, "write to RO SOUT must be ignored"
    assert await rd(bfm, 0x83) == 0, "unmapped offset reads 0"
    await wr(bfm, 0x83, 0xFFFF)
    assert await rd(bfm, SAMPLE) == 1000, "write to unmapped offset must not disturb registers"
