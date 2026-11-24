# q_variant.sdc: brief 207 constraint variants for Quartus (the counterpart of measure_vivado.tcl's variants).
# The variant and clk_b period come from the environment (Q207_VARIANT = N | U | D | DU; Q207_PB = clk_b period in ns), so the
# same file serves the fitter (SDC_FILE) and the analysis re-runs (q_sta.tcl reads it again with another variant).
# D in Quartus Standard: there is no -datapath_only, so each crossing gets set_max_delay at the latency bound L (clock skew
# included), set_min_delay at -L (no hold requirement in practice), set_net_delay -max L on the crossing net (Altera's
# CDC advice, Pro Timing Analyzer "Constraining CDC paths", snippet), and set_max_skew at S on the multi-bit ones. No clock
# group and no false path over the pair: both cut set_max_skew (Quartus help, set_max_skew).
set v  "N";     if {[info exists ::env(Q207_VARIANT)]} { set v $::env(Q207_VARIANT) }
set pb 6.400;   if {[info exists ::env(Q207_PB)]}      { set pb $::env(Q207_PB) }
set pa 10.000
create_clock -name clk_a -period $pa [get_ports clk_a]
create_clock -name clk_b -period $pb [get_ports clk_b]
derive_clock_uncertainty

proc q207_uncert {pa pb} {
    set ua [expr {0.125 * $pa}]; set ub [expr {0.125 * $pb}]
    foreach k {-setup -hold} {
        set_clock_uncertainty -add $k -from [get_clocks clk_a] -to [get_clocks clk_a] $ua
        set_clock_uncertainty -add $k -from [get_clocks clk_b] -to [get_clocks clk_b] $ub
        set_clock_uncertainty -add $k -from [get_clocks clk_a] -to [get_clocks clk_b] $ub
        set_clock_uncertainty -add $k -from [get_clocks clk_b] -to [get_clocks clk_a] $ua
    }
}
# name  from  to  source-clock  L-kind  S-kind  (the same table as measure_vivado.tcl)
set q207_cr {
    lvl   {lvl_a}        {lvl_s1}        a dst   -
    tgl   {tg_a}         {tg_s1}         a dst   -
    wptr  {wgray_a[*] wbin_a[*]} {wq1_b[*]} a src min
    rptr  {rgray_b[*] rbin_b[*]} {rq1_a[*]} b src min
    hsreq {req_a}        {rq1_b}         a dst   -
    hsack {ack_b}        {aq1_a}         b dst   -
    hsdat {hs_hold_a[*]} {hs_data_b[*] hs_data_b[*]~reg0}  a dstN3 dstN3
    cfgt  {ctg_a}        {ct1_b}         a dst   -
    cfgd  {cfg_hold_a[*]} {cfg_b[*] cfg_b[*]~reg0}     a dstN2 dstN2
    ram   {*mem_rtl_0*porta*} {dout_b[*] dout_b[*]~reg0} a src -
}
proc q207_bound {kind s pa pb} {
    set ps [expr {$s eq "a" ? $pa : $pb}]; set pd [expr {$s eq "a" ? $pb : $pa}]
    switch -glob -- $kind {
        src { return $ps }  dst { return $pd }  min { return [expr {min($ps, $pd)}] }
        dstN* { return [expr {[string range $kind 4 end] * $pd}] }
    }
}
proc q207_regs {pats} {
    set c [get_keepers -nowarn [lindex $pats 0]]
    foreach p [lrange $pats 1 end] { set c [add_to_collection $c [get_keepers -nowarn $p]] }
    return $c
}
# DD: the clock-group style with set_max_skew, analysis only: does a clock group cut set_max_skew (help text)?
# set_data_delay is NOT used: 25.1std has the command, but its Timing Analyzer rejects it (measured 2026-11-24, q_cv_good_D_s1:
# "Error (332000): The set_data_delay constraint is not supported in the Legacy Timing Analyzer").
proc q207_dd {cr pa pb} {
    set_clock_groups -asynchronous -group [get_clocks clk_a] -group [get_clocks clk_b]
    foreach {n f t s lk sk} $cr {
        set fc [q207_regs $f]; set tc [q207_regs $t]
        if {[get_collection_size $fc] == 0 || [get_collection_size $tc] == 0} { continue }
        if {$sk ne "-"} { set_max_skew -from $fc -to $tc [q207_bound $sk $s $pa $pb] }
    }
}
proc q207_bounds {cr pa pb m} {
    foreach {n f t s lk sk} $cr {
        set fc [q207_regs $f]; set tc [q207_regs $t]
        if {[get_collection_size $fc] == 0 || [get_collection_size $tc] == 0} { post_message -type warning "q207: $n has no cells"; continue }
        set L [expr {[q207_bound $lk $s $pa $pb] - $m}]
        set_max_delay -from $fc -to $tc $L
        set_min_delay -from $fc -to $tc [expr {-$L}]
        set_net_delay -max -from $fc -to $tc $L
        if {$sk ne "-"} { set_max_skew -from $fc -to $tc [expr {[q207_bound $sk $s $pa $pb] - $m}] }
    }
}
switch -- $v {
    N  { set_clock_groups -asynchronous -group [get_clocks clk_a] -group [get_clocks clk_b] }
    U  { set_clock_groups -asynchronous -group [get_clocks clk_a] -group [get_clocks clk_b]; q207_uncert $pa $pb }
    D  { q207_bounds $q207_cr $pa $pb 0.0 }
    DU { q207_bounds $q207_cr $pa $pb 0.0; q207_uncert $pa $pb }
    DD { q207_dd $q207_cr $pa $pb }
    default { post_message -type error "q207: unknown variant $v" }
}
