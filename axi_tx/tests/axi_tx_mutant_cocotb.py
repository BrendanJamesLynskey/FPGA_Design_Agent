"""The memory target with WSTRB ignored (axil_mem_model BUG=1): no protocol rule fires, the scoreboard catches it."""
from __future__ import annotations

import cocotb

from axi_tx.tests.axi_tx_cocotb import run


@cocotb.test()
async def scoreboard_catches_ignored_wstrb(dut):
    r, _ = await run(dut, "bram_strobes", tag="bram_strobes_memmutant")
    assert sum(r["lite_rules"]["counts"].values()) == 0, r["lite_rules"]
    assert r["sb_mism"] > 0 and r["first_mismatch_txn"] >> 31, r
