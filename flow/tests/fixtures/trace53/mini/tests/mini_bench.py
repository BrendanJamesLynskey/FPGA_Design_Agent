"""Brief 53 fixture bench: the traceability tool reads the tags statically; nothing here is simulated."""
import cocotb

from flow.req import req


@req("REQ-01")
@cocotb.test()
async def counts_and_wraps(dut):
    pass


# req: REQ-02
@cocotb.test()
async def holds_when_disabled(dut):
    pass


# robustness: reset in the middle of counting; the spec says nothing about it
@cocotb.test()
async def reset_mid_count(dut):
    pass


# structural: exports the functional-coverage database; checks nothing
@cocotb.test()
async def zz_export(dut):
    pass
