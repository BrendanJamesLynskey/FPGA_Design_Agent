"""Brief 07a2 fix 2: a top-level port must be a master-XDC name or a bus of one (FDA-CON-7).

Run 2 of c14_int8_dot_requant made a scalar port ``LED0`` (spec.md says "LED0 shows the ready flag"); the master XDC
and the bench use bus ``LED``. ``fixtures/run2_c14_led0.xdc`` is that run's design.xdc."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.core import constraints as con
from agent.core import dispatch
from agent.tests.test_05c2_fixes import rt  # noqa: F401  (the runtime fixture)

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "boards" / "nexys_a7_100t"
RUN2 = (Path(__file__).parent / "fixtures" / "run2_c14_led0.xdc").read_text()


def rules(text: str) -> list[dict]:
    return [x for x in con.check_xdc(text, BOARD) if x["rule"] == "FDA-CON-7"]


def test_run2_top_is_rejected_with_the_master_form() -> None:
    found = rules(RUN2)
    assert len(found) == 1 and "LED0" in found[0]["text"]
    msg = found[0]["message"]
    assert "LED[0]" in msg and "bus LED" in msg


def test_run2_top_with_the_bus_form_passes() -> None:
    fixed = RUN2.replace("get_ports { LED0 }", "get_ports { LED[0] }")
    assert rules(fixed) == []
    assert [x for x in con.check_xdc(fixed, BOARD)] == []


def _xdc(port: str, master: str) -> str:
    pin = [l for l in (BOARD / "Nexys-A7-100T-Master.xdc").read_text().splitlines()
           if f"get_ports {{ {master} }}" in l and "PACKAGE_PIN" in l][0].lstrip("#")
    return pin.replace(f"get_ports {{ {master} }}", f"get_ports {{ {port} }}")


@pytest.mark.parametrize("port,master", [("JA1", "JA[1]"), ("QSPI_DQ0", "QSPI_DQ[0]"), ("ACL_INT1", "ACL_INT[1]"),
                                         ("JB3", "JB[3]"), ("LED[3]", "LED[3]"), ("CPU_RESETN", "CPU_RESETN"),
                                         ("LED16_B", "LED16_B")])
def test_benchmark_scalar_conventions_and_master_names_stay_valid(port: str, master: str) -> None:
    assert rules(_xdc(port, master)) == []


@pytest.mark.parametrize("port,master", [("SW2", "SW[2]"), ("LED15", "LED[15]"), ("led_o", "LED[1]"),
                                         ("clk", "CLK100MHZ"), ("btn_c", "BTNC")])
def test_other_names_are_rejected(port: str, master: str) -> None:
    found = rules(_xdc(port, master))
    assert len(found) == 1 and found[0]["rule"] == "FDA-CON-7"


def test_check_constraints_tool_reports_it(rt) -> None:
    (rt.session.design / "design.xdc").write_text(RUN2)
    r = dispatch(rt.session, "check_constraints", {})
    assert not r["ok"] and any(x["rule"] == "FDA-CON-7" for x in r["findings"])
    assert "LED[0]" in r["output"]


def test_board_constraints_with_a_scalar_led_port_is_not_ok(rt) -> None:
    r = dispatch(rt.session, "board_constraints", {"map": [{"resource": "clk100", "port": "CLK100MHZ"},
                                                           {"resource": "led[0]", "port": "LED0"}]})
    assert not r["ok"] and "LED[0]" in r["output"]
