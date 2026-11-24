"""The packaged harness of fft_real_axis (arith brief 161, owner decision 24): run standalone against the repository's own variants with the SystemVerilog checkers beside them it passes and meets its coverage
targets; against a planted fault, or with a wrong latency, it fails; its generated files are current (Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import suite


@pytest.mark.parametrize("variant", suite.variant_ids("fft_real_axis"))
def test_harness_passes_against_the_repository_rtl(variant):
    suite.check_harness_fft_passes("fft_real_axis", variant)


def test_harness_catches_a_planted_fault_and_a_wrong_latency():
    suite.check_harness_fft_catches("fft_real_axis", "pack_out")


def test_harness_files_are_generated_and_the_checker_top_elaborates():
    suite.check_harness_fft_files("fft_real_axis")
