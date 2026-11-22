"""The bench is sensitive to each log2 variant's stated latency: with the right latency it passes, with two clocks more it fails (arith brief 139d; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant", suite.variant_ids("log2"))
def test_latency_is_exact(variant):
    suite.check_latency_is_exact("log2", variant, ac.load_spec("log2")["variants"][variant]["random_points"][0])
