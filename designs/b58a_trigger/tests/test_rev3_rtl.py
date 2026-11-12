import pytest
from flow import cocotb_run
from designs.b58a_trigger.tests.test_b58a_rtl import SOURCES, HERE

@pytest.mark.parametrize("spec", [1, 0])
def test_rev3(spec):
    cocotb_run.run(f"rev3_{spec}", "trigger_core", SOURCES, "rev3_cocotb", HERE,
                   parameters={"BUILD_MODE": 0, "MDIO_DIV": 4}, extra_env={"PYTHONPATH": str(HERE.parents[2]), "REV_SPEC": str(spec)})
