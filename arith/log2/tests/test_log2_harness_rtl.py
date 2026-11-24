"""The packaged harness (arith/log2/harness, brief 139d, owner decision 24) run standalone against the repository's own variants, with the SystemVerilog
checker beside them, and against a planted fault (Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import suite


def test_harness_files_are_current_and_the_checker_lints():
    suite.check_harness_files("log2")


@pytest.mark.parametrize("variant,params,mode", suite.harness_cases("log2"))
def test_harness_passes_on_every_variant(variant, params, mode):
    suite.check_harness_passes("log2", variant, params, mode)


def test_harness_catches_a_planted_fault():
    suite.check_harness_catches_a_fault("log2", "l_slope_zero")
