"""Brief 140: the flow's fixes for a build that holds AMD debug IP (dbg_xvc): the exception AMD's CDC-15 waiver hides from report_cdc is
read from the timing exceptions, and output pins with no load are no unconstrained endpoint. No Vivado needed."""

from __future__ import annotations

from pathlib import Path

from flow import cdc_structure, gates

HDR = "# cdc_paths v1\nCLOCK|clk_u|10.000|clk_25\nCLOCK|rxusr2|6.206|sfp\n"
PATH = ("PATH|u_core/u_hs/dest_hsdata_ff_reg[{i}]|FDRE|D|rxusr2||u_core/u_hs/src_hsdata_ff_reg[{i}]|FDRE|clk_u|1|0|0|"
        "u_core/u_hs/dest_hsdata_ff_reg[{i}]\n")


def _paths(xexc: bool) -> str:
    return HDR + "".join(PATH.format(i=i) for i in range(4)) + ("XEXC|u_core/u_hs|Max Delay Datapath Only\n" if xexc else "") + "# end\n"


def test_handshake_with_no_report_cdc_row_is_judged_by_the_timing_exception() -> None:
    rep = cdc_structure.classify(cdc_structure.parse_paths(_paths(True)), [])
    assert rep["pass"] and rep["summary"] == {"handshake": 4}


def test_handshake_with_no_report_cdc_row_and_no_exception_still_fails() -> None:
    rep = cdc_structure.classify(cdc_structure.parse_paths(_paths(False)), [])
    assert not rep["pass"] and {u["rule"] for u in rep["unsafe"]} == {"U5"}


def test_unloaded_output_pins_are_not_unconstrained_endpoints() -> None:
    counts = {"no_clock": 3}
    ports = {"no_clock": ["u_dbg/u_ps/inst/PS8_i/EMIOSPI0SCLKO", "u_dbg/u_ps/inst/PS8_i/EMIOSPI1SCLKO", "u_x/ff/C"]}
    assert not gates.unconstrained_ok(counts, ports, set())
    # two outputs with no load are excused, the clock pin of a register is not
    assert not gates.unconstrained_ok(counts, ports, set(), {"u_dbg/u_ps/inst/PS8_i/EMIOSPI0SCLKO", "u_dbg/u_ps/inst/PS8_i/EMIOSPI1SCLKO"})
    assert gates.unconstrained_ok({"no_clock": 2}, {"no_clock": ports["no_clock"][:2]}, set(), set(ports["no_clock"][:2]))


def _row(pos, frm, to, status, through="*"):
    return {"position": pos, "From": frm, "Through": through, "To": to, "Setup": "false", "Hold": "false", "Status": status}


def test_ignored_amd_xpm_templates_are_information_only_when_the_reason_is_benign() -> None:
    from flow import exceptions_check as ec
    single = "[get_cells {syncstages_ff_reg[0]}]"
    assert ec.is_xpm_scoped_exception(_row(120, "*", single, "Non-existent path"), 79, set())
    assert ec.is_xpm_scoped_exception(_row(127, "*", single, "Totally overridden path by FP 79"), 79, {120})
    # a wrapped cell expression is the same row
    assert ec.is_xpm_scoped_exception(_row(127, "*", "[get_cells {syncstages_ff\n_reg[0]}]", "Totally overridden path by FP 79"), 79, set())


def test_ignored_amd_xpm_templates_still_fail_when_they_should() -> None:
    from flow import exceptions_check as ec
    single = "[get_cells {syncstages_ff_reg[0]}]"
    assert not ec.is_xpm_scoped_exception(_row(70, "*", single, "Non-existent path"), 79, set())                    # at one of our positions
    assert not ec.is_xpm_scoped_exception(_row(120, "*", "[get_cells {my_reg[0]}]", "Non-existent path"), 79, set())   # not AMD's text
    assert not ec.is_xpm_scoped_exception(_row(120, "*", single, "Invalid endpoint"), 79, set())                      # another reason
    assert not ec.is_xpm_scoped_exception(_row(127, "*", single, "Totally overridden path by FP 120"), 79, {120})   # overrider itself ignored


def test_crossings_inside_amd_debug_cores_are_listed_not_failed_but_a_crossing_into_one_is_checked() -> None:
    hub = "dbg_hub/inst/BSCANID.u_xsdbm_id/CORE_XSDB.UUT_MASTER/U_ICON_INTERFACE/U_CMD1/ctl_reg_reg[0]"
    hub_src = "dbg_hub/inst/BSCANID.u_xsdbm_id/CORE_XSDB.UUT_MASTER/U_ICON_INTERFACE/icn_cmd_en_reg[0]"
    inside = f"PATH|{hub}|FDRE|D|clk_u||{hub_src}|FDRE|rxusr2|1|0|1|x\\n"
    into = f"PATH|{hub}|FDRE|D|clk_u||u_core/our_reg|FDRE|rxusr2|1|0|1|x\\n"
    rep = cdc_structure.classify(cdc_structure.parse_paths(HDR + inside + "# end\\n"), [])
    assert rep["pass"] and rep["summary"] == {"debug ip": 1}
    rep = cdc_structure.classify(cdc_structure.parse_paths(HDR + into + "# end\\n"), [])
    assert not rep["pass"] and {u["rule"] for u in rep["unsafe"]} == {"U2"}


PLACE_FX = __import__("pathlib").Path(__file__).parent / "fixtures" / "place_hold" / "dbg_xvc_place_summary.rpt"


def test_place_hold_split_reads_dbg_xvc_clock_tables() -> None:
    """The measured placement-stage tables of dbg_xvc (Vivado 2026.1): design WHS -2.723 ns all inside the debug bridge's TCK clocks."""
    t = PLACE_FX.read_text()
    assert gates.parse_timing_summary(t)["whs_ns"] == -2.723
    sp = gates.place_hold_split(t)
    assert sp["worst_debug_ip_ns"] == -2.723 and sp["worst_outside_debug_ip_ns"] == -0.222
    assert len(sp["debug_ip_clocks"]) == 2


def test_place_hold_split_keeps_the_design_wide_value_when_the_tables_do_not_agree() -> None:
    t = PLACE_FX.read_text().replace("-2.576", "-9.999")          # a clock-table row worse than the design summary: cannot be trusted
    assert gates.place_hold_split(t) is None


def test_a_hold_violation_outside_the_debug_clocks_still_fails_the_gate() -> None:
    """Same tables with the design's own clk_u worse than the limit: the split gives that value to the gate, not the debug clocks'."""
    t = PLACE_FX.read_text().replace("-0.222", "-0.700")
    sp = gates.place_hold_split(t)
    assert sp["worst_outside_debug_ip_ns"] == -0.7 and sp["worst_outside_debug_ip_ns"] <= gates.PLACE_WHS_MIN_NS


def test_unloaded_noclock_proc_ignores_the_next_checks_heading_and_keeps_only_output_pins(tmp_path) -> None:
    """flow/build.tcl fda_unloaded_noclock, run under tclsh with stubbed Vivado queries: a check_timing report with 0 no_clock pins writes
    nothing (the dashed heading of the next check is not a pin; found in the first eyescan run), and with pins writes the visible
    output pins with no load."""
    import shutil
    import subprocess

    import pytest
    tclsh = shutil.which("tclsh")
    if tclsh is None:
        pytest.skip("tclsh not installed")
    flow = Path(gates.__file__).parent
    src = (flow / "build.tcl").read_text()
    proc = src[src.index("proc fda_unloaded_noclock"):src.index("proc exception_reports")]
    zero = "1. checking no_clock (0)\n------------------------\n There are 0 register/latch pins with no clock.\n\n\n2. checking constant_clock (0)\n------------------------------\n"
    two = ("1. checking no_clock (2)\n---\n There are 2 register/latch pins with no clock (HIGH)\n\nu_dbg/u_ps/inst/PS8_i/EMIOSPI0SCLKO\n"
           "u_x/<hidden>/y\n\n2. checking constant_clock (0)\n----\n")
    (tmp_path / "zero.rpt").write_text(zero)
    (tmp_path / "two.rpt").write_text(two)
    (tmp_path / "t.tcl").write_text(
        "proc get_pins {args} { set n [lindex $args end]; if {[string match *EMIO* $n]} { return $n }; return {} }\n"
        "proc get_property {p prop} { return OUT }\nproc get_nets {args} { return {} }\n" + proc +
        f"fda_unloaded_noclock {tmp_path}/zero.rpt {tmp_path}/zero.txt\nfda_unloaded_noclock {tmp_path}/two.rpt {tmp_path}/two.txt\n")
    subprocess.run([tclsh, str(tmp_path / "t.tcl")], check=True)
    assert (tmp_path / "zero.txt").read_text() == ""
    assert (tmp_path / "two.txt").read_text().split() == ["u_dbg/u_ps/inst/PS8_i/EMIOSPI0SCLKO"]
