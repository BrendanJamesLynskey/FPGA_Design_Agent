"""Brief 45: the exception gate and the ILA core's own scoped constraints. The fixture is the trimmed route-stage reports of
a real ILA build of t1_dimmer_counter (Vivado 2025.2, flow/tests/fixtures/ila_exceptions/golden/ila_base): 15 ignored
"Non-existent path" exceptions from the ILA core, positions 16-48, after the 5 timing commands of our XDC. No Vivado needed."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from flow import exceptions_check as ec
from flow import gates

FX = Path(__file__).parent / "fixtures" / "ila_exceptions"
GOLD = FX / "golden" / "ila_base"
XDC = [FX / "xdc" / "t1_dimmer_counter.xdc"]
# a real brief 20 fault row (tex_e6b, Vivado 2025.2): a multicycle that covers no path, at one of OUR positions
FAULT_ROW = "POS         [get_cells {{a_reg[*]} {b_reg[*]}}]  *               [get_cells en_reg]  cycles=2        -               Non-existent path\n"


def _copy(tmp: Path) -> Path:
    d = tmp / "build"
    shutil.copytree(GOLD, d)
    return d


def _append(d: Path, row: str) -> None:
    p = d / "exceptions_ignored_route.rpt"
    p.write_text(p.read_text().rstrip("\n") + "\n" + row)


def test_the_real_ila_build_passes_and_reports_the_debug_rows_as_information() -> None:
    r = ec.evaluate(GOLD, "route", XDC)
    assert r["pass"] and r["failures"] == []
    assert r["ignored"] == 15 and len(r["info"]) == 15
    assert {i["rule"] for i in r["info"]} == {"EXC-IGNORED-DEBUG-IP"}
    assert [i["position"] for i in r["info"]][:3] == [16, 17, 18] and all(i["position"] > 5 for i in r["info"])
    assert all(i["status"] == "Non-existent path" for i in r["info"])


def test_the_ila_rows_fail_as_before_without_the_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bug this brief fixes, kept as a control: with the debug-core rule off, the same reports fail 15 times."""
    monkeypatch.setattr(ec, "is_debug_ip_exception", lambda row, last: False)
    r = ec.evaluate(GOLD, "route", XDC)
    assert not r["pass"] and [f["rule"] for f in r["failures"]] == ["EXC-IGNORED"] * 15


def test_an_ila_build_with_a_fault_in_our_xdc_still_fails_and_names_it(tmp_path: Path) -> None:
    d = _copy(tmp_path)
    _append(d, FAULT_ROW.replace("POS", "2"))
    r = ec.evaluate(d, "route", XDC)
    assert not r["pass"] and len(r["info"]) == 15
    (f,) = r["failures"]
    assert (f["rule"], f["position"], f["file"], f["line"]) == ("EXC-IGNORED", 2, "t1_dimmer_counter.xdc", 85)
    assert f["text"].startswith("set_input_delay")


def test_a_debug_looking_row_at_one_of_our_positions_fails(tmp_path: Path) -> None:
    """No waiver by text alone: the same ILA-named row, moved to position 3 (our set_false_path), fails."""
    d = _copy(tmp_path)
    p = d / "exceptions_ignored_route.rpt"
    t = p.read_text().replace("\n16        ", "\n3         ", 1)
    p.write_text(t)
    r = ec.evaluate(d, "route", XDC)
    assert ("EXC-IGNORED", 3, 86) in [(f["rule"], f["position"], f["line"]) for f in r["failures"]]
    assert len(r["info"]) == 14   # (the coverage report still lists position 16 with no endpoints: EXC-NO-PATH, as it should)


def test_a_row_after_our_positions_that_is_not_a_debug_core_fails(tmp_path: Path) -> None:
    d = _copy(tmp_path)
    _append(d, FAULT_ROW.replace("POS", "60"))
    r = ec.evaluate(d, "route", XDC)
    assert [(f["rule"], f["position"], f["file"]) for f in r["failures"]] == [("EXC-IGNORED", 60, None)]


def test_a_row_mixing_a_debug_pattern_with_ours_fails(tmp_path: Path) -> None:
    d = _copy(tmp_path)
    _append(d, "61        [get_cells -hierarchical -filter { NAME =~ \"*ila_core_inst/x_reg*\" }]  *  "
               "[get_cells -hierarchical -filter { NAME =~ \"*dimmer/led_reg*\" }]  false  false  Non-existent path\n")
    r = ec.evaluate(d, "route", XDC)
    assert [f["position"] for f in r["failures"]] == [61]


def test_pattern_parser_survives_the_table_wrapping() -> None:
    row = {"position": 16, "From": '[get_cells -hierarchical -filter { NAME =~  "*ila_core_inst/u_ila_regs/reg_1a/I_ EN_CTL_EQ1.U_CTL/x*" }]',
           "Through": "*", "To": "[get_pins -hierarchical -filter {NAME =~ *ila_core_inst/u_trig/N_DDR_TC.N_DDR_TC _INST[*].U_TC/D}]"}
    assert ec._name_patterns(row) == ["*ila_core_inst/u_ila_regs/reg_1a/I_EN_CTL_EQ1.U_CTL/x*",
                                      "*ila_core_inst/u_trig/N_DDR_TC.N_DDR_TC_INST[*].U_TC/D"]
    assert ec.is_debug_ip_exception(row, 5) and not ec.is_debug_ip_exception(row, 16)
    assert not ec.is_debug_ip_exception({"position": 9, "From": "[get_ports clk]", "Through": "*", "To": "*"}, 5)


def test_the_gate_passes_the_ila_build(tmp_path: Path) -> None:
    d = _copy(tmp_path)
    ex: dict[str, bool] = {}
    # gates._exceptions reads the XDC files from prepare.json, which a trimmed fixture does not carry: point it at ours
    (d / "prepare.json").write_text('{"files": ["flow/tests/fixtures/ila_exceptions/xdc/t1_dimmer_counter.xdc"]}')
    r = gates._exceptions(d, "route", True, ex, "exceptions_clean")
    assert ex == {"exceptions_clean": True} and r["pass"] and len(r["info"]) == 15
