"""The seeded faults of verif/mutants.yaml: the bench kills every one (arith brief 139d; Icarus + cocotb)."""
from __future__ import annotations

from arith.tools import suite


def test_every_mutant_is_killed():
    suite.check_mutants("atan2_mag")
