"""ip_lib/mdio_master under cocotb + Icarus against a clause 22 PHY model (ip_lib/mdio_master/model.py) at three
MDC dividers, and its elaboration guards. NET_RTL_MDIO_MASTER points the tests at a seeded-fault copy."""
from __future__ import annotations

from pathlib import Path

import pytest

from flow import cocotb_run
from flow.net import sim

ROOT = Path(__file__).resolve().parents[3]
TB = ROOT / "ip_lib" / "mdio_master" / "tb"


@pytest.mark.parametrize("div", [32, 2, 5])
def test_mdio(div):
    cocotb_run.run(f"mdio_div{div}", "mdio_master", sim.rtl("mdio_master"), "mdio_cocotb", TB, parameters={"DIV": div},
                   extra_env={"PYTHONPATH": str(ROOT)})


@pytest.mark.parametrize("params", [{"DIV": 1}, {"DIV": 1025}])
def test_mdio_guards(params):
    bad, out = sim.elaborate_fails(sim.rtl("mdio_master"), "mdio_master", params)
    assert bad, out
