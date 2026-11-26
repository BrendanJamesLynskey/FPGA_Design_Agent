"""k-induction proofs of the slave-side control (gap rule, frame credit, tready) with concurrent SVA properties (SymbiYosys, OSS CAD Suite; arith brief 168; jobs in formal/jobs.yaml)."""
from __future__ import annotations

import pytest

from arith.tools import suite


@pytest.mark.parametrize("name", suite.formal_job_params("fft_mdc2_axis", "proof"))
def test_formal_job(name):
    suite.check_formal_job("fft_mdc2_axis", name)
