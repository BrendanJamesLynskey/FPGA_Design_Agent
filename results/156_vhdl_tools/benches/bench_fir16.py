"""fir16 (the larger design: 16-tap FIR, package + record/array types + generate + 4-level adder tree, 7-clock latency): random and
corner-case samples against an integer golden model, with valid gaps; a coefficient rewrite between two streams (written while the
pipeline is empty); the latency of an isolated sample; the saturation flag."""
import cocotb
from cocotb.triggers import ReadOnly, RisingEdge
from common import Trace, ops, rng, start_clock

HALF = (-12, 7, 31, 78, 152, 241, 329, 391)
COEF0 = list(HALF) + list(reversed(HALF))
LAT = 7


def golden(coefs, line):
    y = sum(c * s for c, s in zip(coefs, line)) >> 10
    return max(-32768, min(32767, y)), (y > 32767 or y < -32768)


def s16(v):
    return v - 65536 if v >= 32768 else v


class Mon:
    def __init__(self, dut):
        self.dut, self.out, self.sat, self.t = dut, [], 0, 0
        cocotb.start_soon(self.run())

    async def run(self):
        while True:
            await RisingEdge(self.dut.clk)
            await ReadOnly()
            self.t += 1
            if self.dut.out_v.value == 1:
                self.out.append((self.t, s16(int(self.dut.out_d.value))))
            self.sat = int(self.dut.sat_seen.value) if str(self.dut.sat_seen.value) in "01" else -1


async def stream(dut, r, mon, coefs, n):
    """n clocks of random input; returns the golden outputs for the valid samples, in order."""
    line, want, sat = [0] * 16, [], False
    for i in range(n):
        if r.random() < 0.9:
            d = r.choice([r.randrange(-32768, 32768), 32767, -32768, 0, r.randrange(-100, 100)])
            dut.in_v.value, dut.in_d.value = 1, d & 0xFFFF
            line = [d] + line[:-1]
            y, s = golden(coefs, line)
            want.append(y)
            sat = sat or s
        else:
            dut.in_v.value = 0
        await RisingEdge(dut.clk)
    dut.in_v.value = 0
    for _ in range(LAT + 3):
        await RisingEdge(dut.clk)
    return want, sat


@cocotb.test()
async def fir_stream(dut):
    await start_clock(dut)
    dut.in_v.value, dut.in_d.value, dut.coef_wr.value = 0, 0, 0
    dut.coef_addr.value, dut.coef_data.value = 0, 0
    tr = Trace("fir16", dut.clk, {"out_v": dut.out_v, "out_d": dut.out_d, "sat": dut.sat_seen})
    dut.rst.value = 1
    for _ in range(4):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    tr.enabled = True
    mon = Mon(dut)
    r = rng()
    n = ops()
    # latency of one isolated sample
    t_in = mon.t + 1
    dut.in_v.value, dut.in_d.value = 1, 1000
    await RisingEdge(dut.clk)
    dut.in_v.value = 0
    for _ in range(LAT + 3):
        await RisingEdge(dut.clk)
    assert len(mon.out) == 1, f"isolated sample produced {len(mon.out)} outputs"
    # seven register stages (delay line, products, four tree levels, output): out_v is high after the 6th edge that follows the sampling edge
    assert mon.out[0][0] - t_in == LAT - 1, f"latency {mon.out[0][0] - t_in} edges after the sampling edge, expected {LAT - 1}"
    assert mon.out[0][1] == golden(COEF0, [1000] + [0] * 15)[0]
    # stream 1, default coefficients (the isolated sample is still in the delay line: flush it with 16 zero samples first)
    for _ in range(16):
        dut.in_v.value, dut.in_d.value = 1, 0
        await RisingEdge(dut.clk)
    dut.in_v.value = 0
    for _ in range(LAT + 3):
        await RisingEdge(dut.clk)
    mon.out.clear()
    want, sat1 = await stream(dut, r, mon, COEF0, n)
    got = [y for _, y in mon.out]
    assert got == want, f"stream 1: {sum(a != b for a, b in zip(got, want))} of {len(want)} outputs differ (got {len(got)})"
    # rewrite the coefficients through the write port, flush, stream 2
    coefs = [r.randrange(-2048, 2048) for _ in range(16)]
    for a, c in enumerate(coefs):
        dut.coef_wr.value, dut.coef_addr.value, dut.coef_data.value = 1, a, c & 0xFFF
        await RisingEdge(dut.clk)
    dut.coef_wr.value = 0
    for _ in range(16):
        dut.in_v.value, dut.in_d.value = 1, 0
        await RisingEdge(dut.clk)
    dut.in_v.value = 0
    for _ in range(LAT + 3):
        await RisingEdge(dut.clk)
    mon.out.clear()
    want, sat2 = await stream(dut, r, mon, coefs, n)
    got = [y for _, y in mon.out]
    assert got == want, f"stream 2: {sum(a != b for a, b in zip(got, want))} of {len(want)} outputs differ (got {len(got)})"
    assert mon.sat == int(sat1 or sat2), f"saturation flag {mon.sat}, expected {int(sat1 or sat2)}"
    tr.finish()
