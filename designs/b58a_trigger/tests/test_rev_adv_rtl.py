"""pytest entry: the adversarial regression tests (rev_adv_cocotb.py), speculative and safe mode."""
import os
import pytest
from flow import cocotb_run
from designs.b58a_trigger.tests.test_b58a_rtl import SOURCES, HERE

@pytest.mark.parametrize("spec", [1, 0])
def test_rev_adv(spec):
    cocotb_run.run(f"rev_adv_{spec}", "trigger_core", SOURCES, "rev_adv_cocotb", HERE,
                   parameters={"BUILD_MODE": 0, "MDIO_DIV": 4}, extra_env={"PYTHONPATH": str(HERE.parents[2]), "REV_SPEC": str(spec)})
