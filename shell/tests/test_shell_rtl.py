"""pytest entry: the shell RTL under cocotb + Icarus, at a fast test line and at the real 115200 baud."""

from __future__ import annotations

from pathlib import Path

from flow import cocotb_run

HERE = Path(__file__).parent
SOURCES = cocotb_run.SHELL_RTL + [HERE / "shell_tb_top.sv"]


def test_shell_fast_line() -> None:
    """Protocol, errors, recovery and 150 random transactions; 8 clocks a bit, 400-clock timeout."""
    cocotb_run.run("shell_fast", "shell_tb_top", SOURCES, "shell_cocotb", HERE,
                   parameters={"CLKS_PER_BIT": 8, "TIMEOUT_CYCLES": 400}, seed=1,
                   testcase=["fixed_registers_and_worked_bytes", "errors_are_answered_and_counted",
                             "sync_hunting_skips_junk", "part_frame_times_out_without_answer",
                             "framing_error_drops_the_frame", "random_transactions_match_the_model"])


def test_shell_line_rate_115200() -> None:
    """Bit timing and ±2 % baud tolerance at the real parameters (868 clocks a bit, 1 ms timeout)."""
    cocotb_run.run("shell_115200", "shell_tb_top", SOURCES, "shell_cocotb", HERE,
                   parameters={"CLKS_PER_BIT": 868, "TIMEOUT_CYCLES": 100_000}, seed=1,
                   testcase=["fixed_registers_and_worked_bytes", "bit_timing_at_line_rate",
                             "receiver_tolerates_two_percent_baud_error"])
