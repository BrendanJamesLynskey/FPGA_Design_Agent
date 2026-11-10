"""Brief 20: FDA-CON-5 for multicycle and datapath-only max delays, and FDA-CON-10 (a -setup N multicycle needs its
-hold N-1), on the XDC files of the timing-exception fixtures and on small inline cases."""

from __future__ import annotations

from pathlib import Path

from agent.core import constraints as con

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "boards" / "nexys_a7_100t"
FX = ROOT / "flow" / "tests" / "fixtures" / "timing_exceptions" / "xdc"


def rules(text: str) -> list[str]:
    return [x["rule"] for x in con.check_xdc(text, BOARD) if x["rule"] in ("FDA-CON-5", "FDA-CON-10")]


def test_fixture_xdcs() -> None:
    want = {"tex_e1": [], "tex_e2": ["FDA-CON-10"], "tex_e3": [], "tex_e8": [], "tex_e8b": [], "tex_e9": [],
            "tex_e10": [], "tex_e10b": [], "tex_e10c": [], "tex_e7": []}
    for name, expect in want.items():
        assert rules((FX / f"{name}.xdc").read_text()) == expect, name


def test_multicycle_needs_a_comment_naming_the_enable() -> None:
    line = "set_multicycle_path 2 -setup -from [get_cells a_reg] -to [get_cells p_reg]\n" \
           "set_multicycle_path 1 -hold -from [get_cells a_reg] -to [get_cells p_reg]\n"
    assert rules(line) == ["FDA-CON-5", "FDA-CON-5"]
    assert rules("# the product needs more time\n" + line) == ["FDA-CON-5", "FDA-CON-5"]
    assert rules("# a and p load on the enable, which is 1 on every second clock\n" + line) == []
    assert rules("# p_en is high one clock in 4\n" + line.replace(" 2 ", " 4 ").replace(" 1 -hold", " 3 -hold")) == []


def test_datapath_only_max_delay_needs_the_synchroniser_named() -> None:
    line = "set_max_delay -datapath_only -from [get_cells g_reg[*]] -to [get_cells s1_reg[*]] 7.000\n"
    assert rules(line) == ["FDA-CON-5"]
    assert rules("# bound it\n" + line) == ["FDA-CON-5"]
    assert rules("# the Gray pointer into the 2-flop synchroniser\n" + line) == []
    assert rules("# input path budget\nset_max_delay -from [get_ports a] 4.0\n") == []     # not datapath-only: no rule


def test_setup_without_hold_and_its_waiver() -> None:
    c = "# p loads on the enable, every second clock\n"
    setup = "set_multicycle_path 2 -setup -end -from [get_cells a_reg] -to [get_cells p_reg]\n"
    assert rules(c + setup) == ["FDA-CON-10"]
    assert rules(c + setup + "set_multicycle_path 1 -hold -end -from [get_cells a_reg] -to [get_cells p_reg]\n") == []
    assert rules(c + setup + "set_multicycle_path 1 -hold -from [get_cells a_reg] -to [get_cells b_reg]\n") == ["FDA-CON-10"]
    assert rules(c + setup + "set_multicycle_path 2 -hold -from [get_cells a_reg] -to [get_cells p_reg]\n") == ["FDA-CON-10"]
    waived = "# p loads on the enable; the hold check stays at its default on purpose (capture register reloads)\n" + setup
    assert rules(waived) == []
