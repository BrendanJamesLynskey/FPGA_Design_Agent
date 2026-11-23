"""Forward then inverse through the RTL returns the input divided by N (scaled mode), for both variants (arith brief 148; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant", suite.variant_ids("fft"))
def test_round_trip(variant):
    p = dict(ac.load_spec("fft")["variants"][variant]["random_points"][0])
    p.update({"SCALE": 1, "ORDER": 0})
    ac.run_point("fft", variant, p, "roundtrip")
