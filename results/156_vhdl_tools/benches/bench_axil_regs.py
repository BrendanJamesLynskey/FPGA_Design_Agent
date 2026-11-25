"""axil_regs (brief 55 translation: AXI4-Lite slave, 4 registers, R3 = R0 xor R1 xor R2): writes with random strobes and reads, a Python model,
with random ready back-pressure on the B and R channels."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge
from common import Trace, ops, rng, sval, is01


async def hs(dut, valid, ready_of) -> None:
    """Hold ``valid`` high until its ready was seen high in the cycle before a rising edge (the handshake edge), then drop it."""
    for _ in range(40):                      # called at a falling edge, with valid just driven: ready is sampled in the same cycle
        if ready_of.value == 1:
            await RisingEdge(dut.clk)
            valid.value = 0
            return
        await FallingEdge(dut.clk)
    raise AssertionError("no ready within 40 clocks")


async def axi_write(dut, r, addr, data, strb):
    await FallingEdge(dut.clk)
    dut.awaddr.value, dut.awvalid.value = addr, 1
    dut.wdata.value, dut.wstrb.value, dut.wvalid.value = data, strb, 1
    # both channels offered together; each handshakes on its own ready
    await cocotb.triggers.Combine(cocotb.start_soon(hs(dut, dut.awvalid, dut.awready)), cocotb.start_soon(hs(dut, dut.wvalid, dut.wready)))
    for _ in range(r.randrange(0, 4)):
        await RisingEdge(dut.clk)
    dut.bready.value = 1
    for _ in range(40):
        await FallingEdge(dut.clk)
        if dut.bvalid.value == 1:
            assert int(dut.bresp.value) == 0, "bresp not OKAY"
            await RisingEdge(dut.clk)
            dut.bready.value = 0
            return
    raise AssertionError("no B response")


async def axi_read(dut, r, addr):
    await FallingEdge(dut.clk)
    dut.araddr.value, dut.arvalid.value = addr, 1
    await hs(dut, dut.arvalid, dut.arready)
    for _ in range(r.randrange(0, 4)):
        await RisingEdge(dut.clk)
    dut.rready.value = 1
    for _ in range(40):
        await FallingEdge(dut.clk)
        if dut.rvalid.value == 1:
            assert is01(dut.rdata), f"rdata metavalue {sval(dut.rdata)}"
            v = int(dut.rdata.value)
            await RisingEdge(dut.clk)
            dut.rready.value = 0
            return v
    raise AssertionError("no R response")


@cocotb.test()
async def axil_random(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for s in ("awvalid", "wvalid", "bready", "arvalid", "rready"):
        getattr(dut, s).value = 0
    dut.awaddr.value = dut.araddr.value = 0
    dut.wdata.value = 0
    dut.wstrb.value = 0
    tr = Trace("axil_regs", dut.clk, {"awready": dut.awready, "wready": dut.wready, "bvalid": dut.bvalid, "arready": dut.arready,
                                      "rvalid": dut.rvalid, "rdata": dut.rdata})
    dut.rst_n.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    tr.enabled = True
    r = rng()
    reg = [0, 0, 0]
    for i in range(ops()):
        k = r.random()
        a = r.randrange(4)
        if k < 0.5 and a < 3:
            d, s = r.randrange(1 << 32), r.randrange(16)
            await axi_write(dut, r, a * 4, d, s)
            for b in range(4):
                if s >> b & 1:
                    reg[a] = (reg[a] & ~(0xFF << 8 * b)) | (d & (0xFF << 8 * b))
        else:
            want = reg[a] if a < 3 else reg[0] ^ reg[1] ^ reg[2]
            got = await axi_read(dut, r, a * 4)
            assert got == want, f"op {i}: read reg {a} got {got:#x} want {want:#x}"
    tr.finish()
