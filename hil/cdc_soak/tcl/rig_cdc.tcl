# rig_cdc.tcl: the crossing exceptions, pblocks and waivers of the CDC soak rig, applied after synthesis
# (non-project flow; sourced by tcl/build.tcl with $rig_counts set). Names follow rtl/rig_copy.sv's convention.
#
# Design section 1: no set_clock_groups (it would override the per-crossing max_delay the Gray and handshake
# variants need). Each correct crossing gets its own exception; each mutant gets only a timing false path (so WNS
# describes the synchronous logic) and a waiver that names it as a deliberate mutant, so the full build's
# report_cdc and report_methodology stay readable. XPM macros carry their own constraints.

proc cells_like {pat} { get_cells -quiet -hierarchical -filter "IS_PRIMITIVE && NAME =~ $pat" }
proc pins_of {cells names} {
    if {[llength $cells] == 0} { return {} }
    set f [join [lmap n $names {string cat "REF_PIN_NAME == $n"}] " || "]
    return [get_pins -quiet -of_objects $cells -filter $f]
}

# --- 1. correct 1-bit synchronisers: false path to the first flop's D (UG949: "set_false_path -to" the first
#        synchroniser stage; ASYNC_REG is on both stages)
set s1 [cells_like *syn_s1*]
set_false_path -to [pins_of $s1 D]
puts "rig_cdc: false path to [llength $s1] synchroniser first stages"

# --- 2. reset bridges: false path to the asynchronous clear/preset (release is synchronous inside the bridge)
set br [cells_like *brg_s*]
set_false_path -to [pins_of $br {CLR PRE}]
puts "rig_cdc: false path to the async reset of [llength $br] bridge flops"

# --- 3. Gray buses (C6, and the C10/C13/M9 FIFO pointers): per bus, max_delay -datapath_only and set_bus_skew
set ngray 0
set groups [dict create]
foreach c [cells_like *gsyn_*] {
    # group by bus: the cell name without its bit index
    regsub {\[\d+\]$} [get_property NAME $c] {} key
    regsub {/g\.r_reg$} $key {} key
    dict lappend groups $key $c
}
dict for {key cs} $groups {
    set ends [pins_of $cs D]
    set starts [get_cells -quiet -of_objects [all_fanin -quiet -startpoints_only -flat $ends]]
    if {[llength $starts] == 0} { continue }
    set_max_delay -datapath_only -from $starts -to $ends 10.000
    set_bus_skew -from $starts -to $ends 5.000
    incr ngray
}
puts "rig_cdc: max_delay + bus_skew on $ngray Gray buses"

# --- 4. data held stable by a handshake (C8, M11) or by FIFO pointers (C10, C13, M9 LUT RAM reads)
set hs [cells_like *hsd_*]
if {[llength $hs]} {
    set_max_delay -datapath_only -from [get_cells -quiet -hierarchical -filter {IS_PRIMITIVE && REF_NAME =~ FD* && NAME =~ *pbs_data*}] \
        -to [pins_of $hs D] 10.000
}
set rr [cells_like *ramrd_*]
set rams [get_cells -quiet -hierarchical -filter {IS_PRIMITIVE && REF_NAME =~ RAMD* && NAME =~ *u_fifo*}]
if {[llength $rr] && [llength $rams]} {
    set_max_delay -datapath_only -from $rams -to [pins_of $rr D] 10.000
}
puts "rig_cdc: max_delay -datapath_only on [llength $hs] handshake and [llength $rr] FIFO-read data flops"

# --- 4b. XPM macros. AMD's scoped constraint scripts (data/ip/xpm/xpm_cdc/tcl/xpm_cdc_*.tcl) were not applied in
#         this non-project flow (the 11b small build timed every XPM crossing as a synchronous path), so the same
#         rules are applied here by cell name: false path to every xpm_cdc_single/sync_rst first stage; for
#         xpm_cdc_gray, max_delay -datapath_only (source period) and bus_skew (smaller period) per instance; for
#         xpm_cdc_handshake, max_delay -datapath_only (source period) on the held data.
proc src_period {cells} {
    set c [get_clocks -quiet -of_objects [get_pins -quiet -of_objects [lindex $cells 0] -filter {REF_PIN_NAME == C}]]
    if {$c eq ""} { return 10.000 }
    return [get_property PERIOD [lindex $c 0]]
}
proc dst_period {pins} {
    set c [get_clocks -quiet -of_objects [get_pins -quiet -of_objects [get_cells -of_objects [lindex $pins 0]] -filter {REF_PIN_NAME == C}]]
    if {$c eq ""} { return 10.000 }
    return [get_property PERIOD [lindex $c 0]]
}
set xs [cells_like *syncstages_ff_reg?0?*]
set_false_path -to [pins_of $xs D]
set nxg 0
set xg [dict create]
foreach c [cells_like *dest_graysync_ff_reg?0?*] {
    regsub {/dest_graysync_ff_reg\[0\]\[\d+\]$} [get_property NAME $c] {} key
    dict lappend xg $key $c
}
dict for {key cs} $xg {
    set ends [pins_of $cs D]
    set starts [get_cells -quiet -of_objects [all_fanin -quiet -startpoints_only -flat $ends]]
    if {[llength $starts] == 0} { continue }
    set ps [src_period $starts]
    set pd [dst_period $ends]
    set_max_delay -datapath_only -from $starts -to $ends $ps
    set_bus_skew -from $starts -to $ends [expr {min($ps, $pd)}]
    incr nxg
}
set nxh 0
set xh [dict create]
foreach c [cells_like *dest_hsdata_ff_reg*] {
    regsub {/dest_hsdata_ff_reg\[\d+\]$} [get_property NAME $c] {} key
    dict lappend xh $key $c
}
dict for {key cs} $xh {
    set ends [pins_of $cs D]
    set starts [get_cells -quiet -of_objects [all_fanin -quiet -startpoints_only -flat $ends] -filter {NAME =~ *src_hsdata_ff_reg*}]
    if {[llength $starts] == 0} { continue }
    set_max_delay -datapath_only -from $starts -to $ends [src_period $starts]
    incr nxh
}
puts "rig_cdc: XPM: false path to [llength $xs] first stages, $nxg Gray instances, $nxh handshake data buses"

# --- 5. mutants: timing false path into each mutant endpoint (D and async reset); nothing else
set mut [cells_like *mut_*]
set_false_path -to [pins_of $mut {D CLR PRE}]
puts "rig_cdc: false path to [llength $mut] mutant endpoint flops"

# --- 6. pblocks: each copy's pbs_* cells in its source pblock, pbd_* in its destination pblock, by class
#        far: X0Y0 -> X1Y3 (opposite corners); near: both sides in one region, X0Y2 or X1Y2 by copy parity (one region
#        could not hold all 180 near copies in the first full build); boundary: X0Y1 -> X1Y1 (adjacent regions)
#        Each pblock gets the SLICE range of its clock region and is made hard (IS_SOFT false): the first small
#        builds placed about half the destination cells outside their soft pblocks.
proc region_slices {r} {
    set xs {}; set ys {}
    foreach s [get_sites -filter "CLOCK_REGION == $r && SITE_TYPE =~ SLICE*"] {
        regexp {SLICE_X(\d+)Y(\d+)} [get_property NAME $s] -> x y
        lappend xs $x; lappend ys $y
    }
    return "SLICE_X[tcl::mathfunc::min {*}$xs]Y[tcl::mathfunc::min {*}$ys]:SLICE_X[tcl::mathfunc::max {*}$xs]Y[tcl::mathfunc::max {*}$ys]"
}
foreach {pb region} {pb_far_s X0Y0 pb_far_d X1Y3 pb_near0 X0Y2 pb_near1 X1Y2 pb_bnd_s X0Y1 pb_bnd_d X1Y1} {
    create_pblock $pb
    set rng [region_slices $region]
    resize_pblock [get_pblocks $pb] -add $rng
    set_property IS_SOFT FALSE [get_pblocks $pb]
    puts "rig_cdc: $pb = $region ($rng)"
}
set cls_of [dict create]
foreach cp [rig_copies $rig_counts] { dict set cls_of [lindex $cp 0] [lindex $cp 4] }
set members [dict create pb_far_s {} pb_far_d {} pb_near0 {} pb_near1 {} pb_bnd_s {} pb_bnd_d {}]
foreach side {pbs pbd} {
    foreach c [get_cells -quiet -hierarchical -filter "IS_PRIMITIVE && NAME =~ *${side}_* && REF_NAME !~ RAM* && REF_NAME !~ RAMB*"] {
        set g [rig_copy_of [get_property NAME $c]]
        if {$g < 0} { continue }
        set cls [dict get $cls_of $g]
        set pb [dict get {far,pbs pb_far_s far,pbd pb_far_d near,pbs pb_near near,pbd pb_near
                          boundary,pbs pb_bnd_s boundary,pbd pb_bnd_d} $cls,$side]
        if {$pb eq "pb_near"} { set pb pb_near[expr {$g % 2}] }
        dict lappend members $pb $c
    }
}
dict for {pb cs} $members {
    if {[llength $cs]} { add_cells_to_pblock [get_pblocks $pb] $cs }
    puts "rig_cdc: $pb [llength $cs] cells"
}

# --- 7. waivers for the mutants (report_cdc and report_methodology), one per mutant endpoint group
set nw 0
set mgroups [dict create]
foreach c $mut {
    regsub {\[\d+\]$} [get_property NAME $c] {} key
    regsub {/g\.r_reg$} $key {} key
    dict lappend mgroups $key $c
}
dict for {key cs} $mgroups {
    set g [rig_copy_of $key]
    set v [lindex [lindex [rig_copies $rig_counts] $g] 1]
    set ends [pins_of $cs {D CLR PRE}]
    foreach id {CDC-1 CDC-2 CDC-4 CDC-6 CDC-7 CDC-10 CDC-11 CDC-13 CDC-14 CDC-15 CDC-16 CDC-17 CDC-26} {
        create_waiver -quiet -type CDC -id $id -to $ends -description "deliberate mutant $v (copy $g), hil/cdc_soak"
    }
    foreach id {TIMING-9 TIMING-10 TIMING-14} {
        create_waiver -quiet -type METHODOLOGY -id $id -objects $cs -description "deliberate mutant $v (copy $g), hil/cdc_soak"
    }
    incr nw
}
puts "rig_cdc: waivers on $nw mutant endpoint groups"

# --- 8. explained waivers on correct crossings: the CDC-6 (multi-bit with ASYNC_REG) rows of Gray buses and the
#        CDC-15 (clock-enable controlled) rows of data held stable by a handshake or FIFO. AMD's XPM scripts waive
#        the same rows for their macros; the hand-built C6/C8/C10/C13 (and M9/M11, whose data path is correct) get
#        the same treatment, with the constraint that makes them safe named in the description.
set gends [pins_of [cells_like *gsyn_*] D]
if {[llength $gends]} {
    create_waiver -quiet -type CDC -id CDC-6 -to $gends -description "correct: Gray-coded bus, set_max_delay -datapath_only + set_bus_skew per bus"
}
set xgends [pins_of [cells_like *dest_graysync_ff_reg?0?*] D]
if {[llength $xgends]} {
    create_waiver -quiet -type CDC -id CDC-6 -to $xgends -description "correct: xpm_cdc_gray (as AMD's xpm_cdc_gray.tcl), max_delay + bus_skew applied here"
}
set hends [pins_of [concat [cells_like *hsd_*] [cells_like *ramrd_*] [cells_like *dest_hsdata_ff_reg*]] D]
if {[llength $hends]} {
    create_waiver -quiet -type CDC -id CDC-15 -to $hends -description "correct: data held stable by a handshake or FIFO pointers, set_max_delay -datapath_only"
}
puts "rig_cdc: explained waivers on [llength $gends] + [llength $xgends] Gray and [llength $hends] held-data endpoints"
