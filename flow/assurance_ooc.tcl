# assurance_ooc.tcl (brief 194): one out-of-context Vivado run for the assurance checks and cost measurements.
#   vivado -mode batch -source flow/assurance_ooc.tcl -tclargs <jobs.tcl>
# <jobs.tcl> sets aj(part), aj(top), aj(period), aj(jobs) = list of {name outdir generics sources impl}; impl is 0 (synthesis only) or 1
# (opt, place, route as well). Per job it writes into outdir:
#   synth_funcsim.v   post-synthesis functional netlist (zero delay; flow/assurance.py simulates it and gives it to eqy)
#   util_synth.rpt, timing_synth.rpt, fsm.txt (the synthesis log lines about FSM extraction), util_route.rpt, timing_route.rpt,
#   route_funcsim.v, route_timesim.v, route.sdf (impl = 1), copies.txt (registers whose name matches a TMR copy, after routing)
#   done.txt          one line "key value" per measured figure
# One thread, as the flow's build.tcl does (UG901; the PC is shared).
set_param general.maxThreads 1
set_param synth.maxThreads 1
source [lindex $argv 0]
proc kv {f k v} { puts $f "$k $v" }
foreach job $aj(jobs) {
    lassign $job name wd generics sources impl
    file mkdir $wd
    set f [open $wd/done.txt w]
    kv $f vivado [version -short]
    set t0 [clock seconds]
    if {[catch {
        create_project -in_memory -part $aj(part)
        foreach s $sources { if {[string match *.v $s]} { read_verilog $s } else { read_verilog -sv $s } }
        set args [list -top $aj(top) -part $aj(part) -mode out_of_context]
        foreach g $generics { lappend args -generic $g }
        synth_design {*}$args
        set t1 [clock seconds]
        kv $f synth_s [expr {$t1 - $t0}]
        create_clock -period $aj(period) -name aclk [get_ports aclk]
        write_verilog -mode funcsim -force $wd/synth_funcsim.v
        report_utilization -file $wd/util_synth.rpt
        report_timing_summary -file $wd/timing_synth.rpt -max_paths 1
        set wns [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
        kv $f wns_synth $wns
        if {$impl} {
            opt_design
            place_design
            route_design
            set t2 [clock seconds]
            kv $f impl_s [expr {$t2 - $t1}]
            report_utilization -file $wd/util_route.rpt
            report_timing_summary -file $wd/timing_route.rpt -max_paths 1
            kv $f wns_route [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
            kv $f whs_route [get_property SLACK [get_timing_paths -max_paths 1 -hold]]
            set cf [open $wd/copies.txt w]
            foreach c [get_cells -hier -filter {IS_SEQUENTIAL && REF_NAME =~ FD*}] { puts $cf "[get_property NAME $c] [get_property REF_NAME $c]" }
            close $cf
            write_verilog -mode funcsim -force $wd/route_funcsim.v
            write_verilog -mode timesim -force -sdf_anno true -sdf_file route.sdf $wd/route_timesim.v
            write_sdf -mode timesim -force $wd/route.sdf
        }
        kv $f ok 1
    } err]} {
        kv $f ok 0
        kv $f error [string map {"\n" " "} $err]
    }
    close $f
    catch {close_project}
}
