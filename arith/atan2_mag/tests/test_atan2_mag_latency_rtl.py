"""The bench is sensitive to each atan2_mag variant's stated latency: with the right latency it passes, with two clocks more it fails (arith brief 139d; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant", suite.variant_ids("atan2_mag"))
def test_latency_is_exact(variant):
    suite.check_latency_is_exact("atan2_mag", variant, ac.load_spec("atan2_mag")["variants"][variant]["random_points"][0])
