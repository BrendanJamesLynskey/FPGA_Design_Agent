"""Formal jobs that refute a planted fault of the control (the properties can fail) (SymbiYosys, OSS CAD Suite; arith brief 168; jobs in formal/jobs.yaml)."""
from __future__ import annotations

import pytest

from arith.tools import suite


@pytest.mark.parametrize("name", suite.formal_job_params("fft_mdc2_axis", "refute"))
def test_formal_job(name):
    suite.check_formal_job("fft_mdc2_axis", name)
