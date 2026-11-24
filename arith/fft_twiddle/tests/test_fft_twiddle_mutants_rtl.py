"""The seeded faults of verif/mutants.yaml: the bench kills every one (arith brief 148; Icarus + cocotb)."""
from __future__ import annotations

from arith.tools import suite


def test_every_mutant_is_killed():
    suite.check_mutants("fft_twiddle", min_valid=6)
