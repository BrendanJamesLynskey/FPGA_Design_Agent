"""Brief 08a (port failure of c14_nexys_tiny_cnn run 1): every port the spec declares, and the USB-UART pair, must
exist on the top module (FDA-CON-8, FDA-CON-9), reported by lint and check_constraints with a clear message.

The run's top sent the answer on UART_RXD_OUT and left out UART_TXD_IN as "unused"; the bench drives UART_TXD_IN, so it
scored 0 of 5. The tests build the same situation on a copy of a repo design."""

from __future__ import annotations

from pathlib import Path

import yaml

from agent.core import constraints as con
from agent.core import dispatch
from agent.core import tools as tl
from agent.graph import run as gr
from agent.tests.test_05c2_fixes import rt  # noqa: F401  (the runtime fixture)

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "boards" / "nexys_a7_100t"

TOP_ONLY_TX = """module cnn_top (input logic CLK100MHZ, input logic CPU_RESETN, input logic BTNC, output logic UART_RXD_OUT);
endmodule
"""
TOP_BOTH = """module cnn_top (input logic CLK100MHZ, input logic CPU_RESETN, input logic BTNC,
  /* verilator lint_off UNUSEDSIGNAL */ input logic UART_TXD_IN, output logic UART_RXD_OUT);
endmodule
"""


def findings(top_ports, spec_ports=(), xdc_ports=None, shell=False):
    return con.check_top_ports("cnn_top", top_ports, list(spec_ports), xdc_ports, BOARD, shell)


def test_uart_pair_with_only_the_transmit_pin_is_rejected_for_a_no_shell_design() -> None:
    f = findings({"CLK100MHZ", "UART_RXD_OUT"})
    assert [x["rule"] for x in f] == ["FDA-CON-9"]
    assert "UART_TXD_IN" in f[0]["message"] and "never" not in f[0]["message"].split("UART_TXD_IN")[0]
    assert "lint_off UNUSEDSIGNAL" in f[0]["message"]


def test_both_pins_pass_and_a_design_without_the_uart_is_left_alone() -> None:
    assert findings({"CLK100MHZ", "UART_RXD_OUT", "UART_TXD_IN"}) == []
    assert findings({"CLK100MHZ", "LED"}) == []


def test_the_test_shell_needs_both_pins() -> None:
    f = findings({"CLK100MHZ", "LED"}, shell=True)
    assert sorted(x["message"].split("declare the port ")[1].split(" ")[0] for x in f) == ["UART_RXD_OUT", "UART_TXD_IN"]
    assert all("test shell" in x["message"] for x in f)


def test_spec_declared_port_missing_from_the_top_is_rejected() -> None:
    f = findings({"CLK100MHZ", "SW"}, spec_ports=["CLK100MHZ", "SW", "BTNC"])
    assert [x["rule"] for x in f] == ["FDA-CON-8"] and "BTNC" in f[0]["message"] and "cnn_top" in f[0]["message"]


def test_bus_bits_in_the_spec_count_as_the_bus() -> None:
    assert findings({"LED"}, spec_ports=con.spec_port_names({"ports": [{"name": "LED[15:0]"}, {"name": "LED"}]})) == []
    assert con.spec_port_names({"ports": {"SW[3]": {}}}) == ["SW"]


def test_xdc_must_constrain_both_pins_when_the_top_has_them() -> None:
    f = findings({"UART_RXD_OUT", "UART_TXD_IN"}, xdc_ports={"UART_RXD_OUT", "CLK100MHZ"})
    assert [x["rule"] for x in f] == ["FDA-CON-9"] and "uart_rx" in f[0]["message"]
    assert findings({"UART_RXD_OUT", "UART_TXD_IN"}, xdc_ports={"UART_RXD_OUT", "UART_TXD_IN"}) == []


def test_no_top_source_yet_reports_nothing() -> None:
    assert findings(None, spec_ports=["BTNC"], shell=True) == []


def _setup(rt, top_text, spec_ports):  # noqa: F811
    d = rt.session.design
    (d / "rtl").mkdir(exist_ok=True)
    for old in (d / "rtl").glob("*.sv"):
        old.unlink()
    (d / "rtl" / "cnn_top.sv").write_text(top_text)
    (d / "spec.yaml").write_text(yaml.safe_dump({"ports": [{"name": n} for n in spec_ports]}))
    rel = d.relative_to(rt.session.root)
    (d / "build.yaml").write_text(yaml.safe_dump({"top": "cnn_top", "part": "xc7a100tcsg324-1",
                                                  "sources": [f"{rel}/rtl/*.sv"], "constraints": [f"{rel}/design.xdc"]}))
    return d


def test_check_constraints_tool_reports_the_missing_uart_pin(rt) -> None:  # noqa: F811
    d = _setup(rt, TOP_ONLY_TX, ["CLK100MHZ", "BTNC", "UART_RXD_OUT"])
    (d / "design.xdc").write_text("")
    ids = [x["rule"] for x in dispatch(rt.session, "check_constraints", {})["findings"]]
    assert "FDA-CON-9" in ids                                   # shell designs: both UART pins are required
    r = dispatch(rt.session, "check_constraints", {})
    assert not r["ok"] and "UART_TXD_IN" in r["output"]


def test_check_constraints_tool_reports_a_spec_port_missing_on_the_top(rt) -> None:  # noqa: F811
    d = _setup(rt, TOP_BOTH, ["CLK100MHZ", "BTNC", "UART_RXD_OUT", "UART_TXD_IN", "SW"])
    (d / "design.xdc").write_text("")
    r = dispatch(rt.session, "check_constraints", {})
    assert any(x["rule"] == "FDA-CON-8" and "SW" in x["message"] for x in r["findings"])


def test_rtl_role_convention_names_both_rules() -> None:
    assert "FDA-CON-8" in gr.CONVENTIONS and "FDA-CON-9" in gr.CONVENTIONS and "UART_TXD_IN" in gr.CONVENTIONS
