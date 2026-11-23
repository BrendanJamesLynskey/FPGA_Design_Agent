"""The AXI4-Stream protocol checkers can fail: a stalled sink on the no-stall variant and a withdrawn tvalid on the stalling variant are counted (arith brief 148; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant", suite.variant_ids("fft_axis"))
def test_checker_flags_a_deliberate_violation(variant):
    ac.run_point("fft_axis", variant, {"LOGN": 4}, "checker")
