"""pytest entry for one agent-supplied transaction program in simulation (agent tool axi_simulate): $AXI_TX_PROGRAM names
the program file, $AXI_TX_RESULT where the results go. Skipped when unset (CI runs the fixed programs instead)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from flow import cocotb_run

HERE = Path(__file__).parent
ROOT = HERE.parents[1]


@pytest.mark.skipif(not os.environ.get("AXI_TX_PROGRAM"), reason="AXI_TX_PROGRAM not set")
def test_axi_tx_program() -> None:
    from axi_tx.tests.test_59a_rtl import SRC
    cocotb_run.run("axi_tx_59a_prog", "axi_tx_tb", SRC, "axi_tx_program_cocotb", HERE, seed=1,
                   extra_env={k: os.environ[k] for k in ("AXI_TX_PROGRAM", "AXI_TX_RESULT")})
