"""Formal jobs of the complex multiplier that are proved for all inputs (k-induction) (SymbiYosys, OSS CAD Suite; arith brief 148; jobs in formal/jobs.yaml)."""
from __future__ import annotations

import pytest

from arith.tools import suite


@pytest.mark.parametrize("name", suite.formal_job_params("fft_cmul", "proof"))
def test_formal_job(name):
    suite.check_formal_job("fft_cmul", name)
