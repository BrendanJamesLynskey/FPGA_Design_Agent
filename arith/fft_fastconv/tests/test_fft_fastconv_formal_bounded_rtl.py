"""Formal jobs of the AXI4-Lite register file, bounded model checks from reset (SymbiYosys, OSS CAD Suite; arith brief 161; jobs in formal/jobs.yaml)."""
from __future__ import annotations

import pytest

from arith.tools import suite


@pytest.mark.parametrize("name", suite.formal_job_params("fft_fastconv", "bounded"))
def test_formal_job(name):
    suite.check_formal_job("fft_fastconv", name)
