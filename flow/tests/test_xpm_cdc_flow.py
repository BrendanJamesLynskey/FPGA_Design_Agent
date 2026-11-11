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
