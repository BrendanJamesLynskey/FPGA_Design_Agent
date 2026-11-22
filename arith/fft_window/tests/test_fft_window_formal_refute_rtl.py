"""Formal jobs of the window multiplier that refute a planted fault (the check can fail) (SymbiYosys, OSS CAD Suite; arith brief 148; jobs in formal/jobs.yaml)."""
from __future__ import annotations

import pytest

from arith.tools import suite


@pytest.mark.parametrize("name", suite.formal_job_params("fft_window", "refute"))
def test_formal_job(name):
    suite.check_formal_job("fft_window", name)
