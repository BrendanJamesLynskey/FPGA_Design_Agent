# q_sta.tcl: brief 207, Timing Analyzer measurements on one fitted cdc207 project, once per analysis variant.
#   quartus_sta -t q_sta.tcl <work dir> <sdc file> <out dir> <clk_b period> <variant> ...
# The fit is fixed; only the analysis constraints change, so a difference between variants here is an analysis effect
# (E1, E4, E5), never a placement one.
package require ::quartus::project
lassign $argv work sdc out pb
set variants [lrange $argv 4 end]
project_open $work/cdc207
file mkdir $out
set cr {
    lvl   {lvl_a}        {lvl_s1}
    tgl   {tg_a}         {tg_s1}
    wptr  {wgray_a[*] wbin_a[*]} {wq1_b[*]}
    rptr  {rgray_b[*] rbin_b[*]} {rq1_a[*]}
    hsreq {req_a}        {rq1_b}
    hsack {ack_b}        {aq1_a}
    hsdat {hs_hold_a[*]} {hs_data_b[*] hs_data_b[*]~reg0}
    cfgt  {ctg_a}        {ct1_b}
    cfgd  {cfg_hold_a[*]} {cfg_b[*] cfg_b[*]~reg0}
    ram   {*mem_rtl_0*porta*} {dout_b[*] dout_b[*]~reg0}
}
proc regs {pats} {
    set c [get_keepers -nowarn [lindex $pats 0]]
    foreach p [lrange $pats 1 end] { set c [add_to_collection $c [get_keepers -nowarn $p]] }
    return $c
}
foreach v $variants {
    set ::env(Q207_VARIANT) $v
    set ::env(Q207_PB) $pb
    set d $out/$v
    file mkdir $d
    set fh [open $d/metrics.txt w]
    puts $fh "# q_sta v1 variant=$v pb=$pb quartus=$::quartus(version)"
    puts $fh "PROBE|set_data_delay=[llength [info commands set_data_delay]]"
    create_timing_netlist
    if {[catch { read_sdc $sdc } e]} { puts $fh "SDC_ERROR|$e" }
    update_timing_netlist
    foreach corner [get_available_operating_conditions] {
        set_operating_conditions $corner
        update_timing_netlist
        set tag [regsub -all {[^A-Za-z0-9]+} $corner _]
        puts $fh "CORNER|$tag"
        foreach {n f t} $cr {
            set fc [regs $f]; set tc [regs $t]
            if {[get_collection_size $fc] == 0 || [get_collection_size $tc] == 0} { puts $fh "CROSS|$tag|$n|nocells"; continue }
            set ps [get_timing_paths -from $fc -to $tc -npaths 200 -setup]
            set ign 0
            if {[get_collection_size $ps] == 0} { catch { set ps [get_timing_paths -from $fc -to $tc -npaths 200 -setup -false_path] ; set ign 1 } }
            set ds {}; set sl {}
            foreach_in_collection p $ps { lappend ds [get_path_info $p -data_delay]; lappend sl [get_path_info $p -slack] }
            if {[llength $ds] == 0} { puts $fh "CROSS|$tag|$n|npaths=0"; continue }
            set ds [lsort -real $ds]; set sl [lsort -real $sl]
            puts $fh [format "CROSS|%s|%s|npaths=%d|ignored=%d|dmax=%.3f|dmin=%.3f|spread=%.3f|slack=%s" $tag $n [llength $ds] $ign \
                [lindex $ds end] [lindex $ds 0] [expr {[lindex $ds end] - [lindex $ds 0]}] [lindex $sl 0]]
        }
        foreach c {clk_a clk_b} {
            set s [get_timing_paths -from_clock [get_clocks $c] -to_clock [get_clocks $c] -setup -npaths 1]
            set h [get_timing_paths -from_clock [get_clocks $c] -to_clock [get_clocks $c] -hold -npaths 1]
            set ws ""; set wh ""
            foreach_in_collection p $s { set ws [get_path_info $p -slack] }
            foreach_in_collection p $h { set wh [get_path_info $p -slack] }
            puts $fh "FILL|$tag|$c|wns=$ws|whs=$wh"
        }
        foreach {x y} {clk_a clk_b clk_b clk_a} {
            set s [get_timing_paths -from_clock [get_clocks $x] -to_clock [get_clocks $y] -setup -npaths 1]
            set ws "none"; foreach_in_collection p $s { set ws [get_path_info $p -slack] }
            puts $fh "INTER|$tag|$x->$y|wns=$ws"
        }
        report_max_skew -file $d/max_skew_$tag.rpt -npaths 20 -detail path_only
        catch { report_net_delay -file $d/net_delay_$tag.rpt }
        report_metastability -file $d/metastability_$tag.rpt -nchains 50
        report_clock_transfers -file $d/clock_transfers_$tag.rpt
    }
    report_sdc -file $d/sdc.rpt
    delete_timing_netlist
    close $fh
}
project_close
