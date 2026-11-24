"""The AXI4-Stream protocol checkers can fail: a pause inside a frame and a withdrawn tvalid are counted (arith brief 168; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite

@pytest.mark.parametrize("variant", suite.variant_ids("fft_mdc2_axis"))
def test_checker_flags_a_deliberate_violation(variant):
    ac.run_point("fft_mdc2_axis", variant, {"LOGN": 5}, "checker")
