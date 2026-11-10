# xpm_cdc.tcl: the timing exceptions AMD's xpm_cdc macros ship in their scoped constraint files, applied by cell name.
#
# QR1 (2026-11-10) found that the non-project flow (read_verilog + synth_design, flow/build.tcl) does not apply
# AMD's scoped XPM constraints (data/ip/xpm/xpm_cdc/tcl/xpm_cdc_*.tcl): a design with one xpm_cdc_single and one
# xpm_cdc_gray between two clocks showed Exception "None" for both crossings in report_cdc and a clk_a -> clk_b
# setup WNS of -1.364 ns (5 failing endpoints), i.e. every XPM crossing was timed as a synchronous path.
# The same rules are applied here, after synth_design, for every xpm_cdc_single / sync_rst first stage, every
# xpm_cdc_gray (max_delay -datapath_only at the source period plus set_bus_skew at the smaller period) and every
# xpm_cdc_handshake data bus. Written from hil/cdc_soak/tcl/rig_cdc.tcl section 4b (proven in the rig build).
# Everything is get_cells -quiet: a design with no XPM macros gets no exception.
#
# Status: the gap was measured for xpm_cdc_single and xpm_cdc_gray (flow/tests/fixtures/xpm_probe). This fix reuses the rig's
# rules (proven there). Re-run on the probe through flow/run_vivado.sh (2026-11-10): report_cdc shows Max Delay Datapath Only
# and False Path on the two rows, clk_a -> clk_b WNS +8.891 ns (was -1.364 ns). xpm_cdc_array_single may match the first-stage pattern by name (not
# checked); xpm_cdc_pulse and xpm_cdc_async_rst get no exception here.

proc xpm_cells_like {pat} { get_cells -quiet -hierarchical -filter "IS_PRIMITIVE && NAME =~ $pat" }
proc xpm_pins_of {cells} {
    if {[llength $cells] == 0} { return {} }
    return [get_pins -quiet -of_objects $cells -filter {REF_PIN_NAME == D}]
}
proc xpm_src_period {cells} {
    set c [get_clocks -quiet -of_objects [get_pins -quiet -of_objects [lindex $cells 0] -filter {REF_PIN_NAME == C}]]
    if {$c eq ""} { return 10.000 }
    return [get_property PERIOD [lindex $c 0]]
}
proc xpm_dst_period {pins} {
    set c [get_clocks -quiet -of_objects [get_pins -quiet -of_objects [get_cells -of_objects [lindex $pins 0]] -filter {REF_PIN_NAME == C}]]
    if {$c eq ""} { return 10.000 }
    return [get_property PERIOD [lindex $c 0]]
}

proc apply_xpm_cdc_constraints {} {
    # xpm_cdc_single, xpm_cdc_sync_rst: false path to the first synchroniser stage
    set xs [xpm_cells_like *syncstages_ff_reg?0?*]
    if {[llength $xs]} { set_false_path -to [xpm_pins_of $xs] }
    # xpm_cdc_gray: per instance, max_delay -datapath_only (source period) and bus skew (smaller period)
    set nxg 0
    set xg [dict create]
    foreach c [xpm_cells_like *dest_graysync_ff_reg?0?*] {
        regsub {/dest_graysync_ff_reg\[0\]\[\d+\]$} [get_property NAME $c] {} key
        dict lappend xg $key $c
    }
    dict for {key cs} $xg {
        set ends [xpm_pins_of $cs]
        set starts [get_cells -quiet -of_objects [all_fanin -quiet -startpoints_only -flat $ends]]
        if {[llength $starts] == 0} { continue }
        set ps [xpm_src_period $starts]
        set pd [xpm_dst_period $ends]
        set_max_delay -datapath_only -from $starts -to $ends $ps
        set_bus_skew -from $starts -to $ends [expr {min($ps, $pd)}]
        incr nxg
    }
    # xpm_cdc_handshake: the held data bus, max_delay -datapath_only at the source period
    set nxh 0
    set xh [dict create]
    foreach c [xpm_cells_like *dest_hsdata_ff_reg*] {
        regsub {/dest_hsdata_ff_reg\[\d+\]$} [get_property NAME $c] {} key
        dict lappend xh $key $c
    }
    dict for {key cs} $xh {
        set ends [xpm_pins_of $cs]
        set starts [get_cells -quiet -of_objects [all_fanin -quiet -startpoints_only -flat $ends] -filter {NAME =~ *src_hsdata_ff_reg*}]
        if {[llength $starts] == 0} { continue }
        set_max_delay -datapath_only -from $starts -to $ends [xpm_src_period $starts]
        incr nxh
    }
    puts "xpm_cdc: false path to [llength $xs] first stages, $nxg Gray instances, $nxh handshake data buses"
}
