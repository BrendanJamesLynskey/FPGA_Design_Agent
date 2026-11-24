"""The register file against the contract (read-only and unmapped addresses, partial strobes, write-1-to-clear, auto-increment, write order, slow response channels, a refused commit while BUSY), with the AXI4-Lite protocol checker (arith brief 161; Icarus + cocotb)."""
from __future__ import annotations

import pytest

from arith.tools import arith_common as ac
from arith.tools import suite


@pytest.mark.parametrize("variant,params", suite.point_params("fft_fastconv", "exhaustive_points")[:3])
def test_register_contract(variant, params):
    ac.run_point("fft_fastconv", variant, params, "axil")
