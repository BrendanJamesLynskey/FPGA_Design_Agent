"""QR1: flow/build.tcl applies the XPM crossing exceptions after synthesis (AMD's scoped constraints are not applied
in the non-project flow; measured 2026-11-10: report_cdc Exception "None", clk_a -> clk_b WNS -1.364 ns)."""
from pathlib import Path

FLOW = Path(__file__).resolve().parents[1]


def test_build_tcl_applies_xpm_constraints_between_synth_and_checkpoint():
    t = (FLOW / "build.tcl").read_text()
    # brief 33: the proc files are sourced once near the top (the resumed flow needs them too); the call stays between
    # synth_design and the checkpoint, so a resumed build's post_synth.dcp already carries the constraints
    i_src = t.index("source $flow_dir/xpm_cdc.tcl")
    i_synth = t.index("synth_design -top")
    i_app = t.index("apply_xpm_cdc_constraints", i_synth)
    i_dcp = t.index("write_checkpoint -force $out/post_synth.dcp")
    i_rep = t.index("report_timing_summary -max_paths 10 -report_unconstrained -file $out/timing_summary_synth.rpt")
    assert i_src < i_synth < i_app < i_dcp < i_rep


def test_xpm_cdc_tcl_covers_the_macros_and_is_quiet_without_them():
    t = (FLOW / "xpm_cdc.tcl").read_text()
    for needle in ("syncstages_ff_reg", "dest_graysync_ff_reg", "set_bus_skew", "dest_hsdata_ff_reg",
                   "set_false_path -to", "set_max_delay -datapath_only"):
        assert needle in t
    # every object query is -quiet so a design without XPM macros gets no exception and no error
    assert "get_cells -hierarchical" not in t.replace("get_cells -quiet -hierarchical", "")
    assert t.count("{") == t.count("}")


def test_xpm_cdc_tcl_applies_nothing_on_a_design_without_xpm_cells(tmp_path):
    """96C: with every Vivado query returning an empty list (a design with no XPM macro and no xpm_fifo_async), the proc
    issues no exception and reports 0 of each (run under tclsh with stubbed Vivado commands; no Vivado needed)."""
    import shutil
    import subprocess
    import pytest
    tclsh = shutil.which("tclsh")
    if tclsh is None:
        pytest.skip("tclsh not installed")
    stub = tmp_path / "stub.tcl"
    stub.write_text(
        "foreach c {get_cells get_pins get_clocks get_property all_fanin all_fanout} { proc $c {args} {return {}} }\n"
        "foreach c {set_max_delay set_false_path set_bus_skew} { proc $c {args} {puts \"UNEXPECTED $c\"} }\n"
        f"source {FLOW / 'xpm_cdc.tcl'}\napply_xpm_cdc_constraints\n")
    out = subprocess.run([tclsh, str(stub)], capture_output=True, text=True, check=True).stdout
    assert "UNEXPECTED" not in out
    assert "0 first stages, 0 Gray instances, 0 handshake data buses, 0 FIFO memories" in out


def test_build_tcl_implements_debug_cores_right_after_synthesis():
    """Brief 140: a design with AMD debug IP gets its hub from implement_debug_core at the synthesis stage (before the XPM exceptions and
    the checkpoint), never for the ILA variant (flow/debug.tcl makes that hub) and never for a design with no debug core."""
    t = (FLOW / "build.tcl").read_text()
    i_synth = t.index("stage synth\n")
    i_impl = t.index("implement_debug_core", i_synth)
    i_app = t.index("apply_xpm_cdc_constraints", i_synth)
    i_dcp = t.index("write_checkpoint -force $out/post_synth.dcp")
    assert i_synth < i_impl < i_app < i_dcp
    assert 'if {$ila eq "0" && [llength [get_debug_cores -quiet]]}' in t


def _tclsh_or_skip():
    import shutil
    import pytest
    tclsh = shutil.which("tclsh")
    if tclsh is None:
        pytest.skip("tclsh not installed")
    return tclsh


AMD_ROWS = ("Position  From   Through  To   Setup  Hold\n"
            "95  *  *  [get_cells {syncstages_ff_reg[0]}]  false  false\n"
            "91  [get_cells src_hsdata_ff_reg*]  *  [get_cells dest_hsdata_ff_reg*]  max_dpo=6.206  -\n")


def _run_xpm(tmp_path, exceptions_text):
    import subprocess
    stub = tmp_path / "stub.tcl"
    cells = "{a/syncstages_ff_reg[0]}" if exceptions_text is not None else "{}"
    stub.write_text(
        "foreach c {get_pins get_clocks get_property all_fanin all_fanout} { proc $c {args} {return {}} }\n"
        "proc get_cells {args} { if {[lsearch $args -hierarchical] >= 0 && [string match *syncstages* $args]} { return {a/syncstages_ff_reg[0]} }; return {} }\n"
        "proc get_pins {args} { return {a/syncstages_ff_reg[0]/D} }\n"
        "foreach c {set_max_delay set_bus_skew} { proc $c {args} {puts \"SET $c\"} }\n"
        "proc set_false_path {args} {puts \"SET set_false_path\"}\n"
        f"proc report_exceptions {{args}} {{ return {{{exceptions_text or ''}}} }}\n"
        f"source {FLOW / 'xpm_cdc.tcl'}\napply_xpm_cdc_constraints\n")
    return subprocess.run([_tclsh_or_skip(), str(stub)], capture_output=True, text=True, check=True).stdout


def test_xpm_cdc_tcl_leaves_a_kind_to_amd_when_amds_own_rows_are_applied(tmp_path):
    """Brief 140: AMD's scoped XPM exceptions already in the list (unscoped pattern, as in dbg_xvc) -> the flow adds no duplicate for that kind."""
    out = _run_xpm(tmp_path, AMD_ROWS)
    assert "SET set_false_path" not in out
    assert "false path to 0 first stages" in out
    assert "single 1 hs 1 gray 0" in out


def test_xpm_cdc_tcl_applies_its_rule_when_amds_rows_are_absent(tmp_path):
    """Without AMD's rows (the eyescan and default builds) the flow's false path is applied exactly as before."""
    out = _run_xpm(tmp_path, "Position  From  Through  To\n3  *  *  [get_pins -filter REF_PIN_NAME=~*D]  false  false\n")
    assert "SET set_false_path" in out
    assert "single 0 hs 0 gray 0" in out
