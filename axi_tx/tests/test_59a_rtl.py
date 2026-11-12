"""pytest entry: the brief 59A transactor under cocotb + Icarus (axi_tx_tb), and the scoreboard against a memory mutant."""
from __future__ import annotations

from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
SRC = sorted((ROOT / "axi_tx" / "rtl").glob("*.sv")) + sorted((ROOT / "ip_lib" / "logic_analyser" / "rtl").glob("*.sv")) \
    + [HERE / "axi_tx_tb.sv"]


def test_axi_tx_transactor_checker_scoreboard() -> None:
    cocotb_run.run("axi_tx_59a", "axi_tx_tb", SRC, "axi_tx_cocotb", HERE, seed=1)


def test_axi_tx_scoreboard_catches_a_memory_mutant() -> None:
    cocotb_run.run("axi_tx_59a_mut", "axi_tx_tb", SRC, "axi_tx_mutant_cocotb", HERE, parameters={"MEM_BUG": 1}, seed=1)
