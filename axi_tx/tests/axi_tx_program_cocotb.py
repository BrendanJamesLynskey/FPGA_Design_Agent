"""One transaction program from $AXI_TX_PROGRAM through the transactor RTL; the results to $AXI_TX_RESULT (axi_simulate)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import cocotb

from axi_tx.host import host, model
from axi_tx.host.program import assemble
from axi_tx.tests.axi_tx_cocotb import boot


@cocotb.test()
async def run_program(dut):
    bfm = await boot(dut)
    prog = assemble(Path(os.environ["AXI_TX_PROGRAM"]))
    r = await host.arun(host.run_program(prog), bfm)
    r["model_compare"] = model.compare(model.run(prog), r["log"])
    r.pop("log_raw", None)
    Path(os.environ["AXI_TX_RESULT"]).write_text(json.dumps(r, indent=1, default=str) + "\n")
    assert "done" in r["status"]["flags"], r["status"]
