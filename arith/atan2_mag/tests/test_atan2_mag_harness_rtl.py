"""The packaged harness (arith/atan2_mag/harness, brief 139d, owner decision 24) run standalone against the repository's own variants, with the SystemVerilog
checker beside them, and against a planted fault (Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import suite


def test_harness_files_are_current_and_the_checker_lints():
    suite.check_harness_files("atan2_mag")


@pytest.mark.parametrize("variant,params,mode", suite.harness_cases("atan2_mag"))
def test_harness_passes_on_every_variant(variant, params, mode):
    suite.check_harness_passes("atan2_mag", variant, params, mode)


def test_harness_catches_a_planted_fault():
    suite.check_harness_catches_a_fault("atan2_mag", "ac_neg_from_y")
