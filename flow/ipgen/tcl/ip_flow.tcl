# ip_flow.tcl: the common Vivado side of every ipgen adapter (brief 19). Batch, no GUI.
#   vivado -mode batch -source flow/ipgen/tcl/ip_flow.tcl -tclargs <cfg.tcl> <stage> [<stage> ...]
# <cfg.tcl> is written by the Python adapter and defines the array ipgen:
#   part, workdir, module, create_args (the create_ip -name/-vendor/-library/-version words), props (CONFIG.* name/value
#   list), tb_file, tb_top, sim_libs_note, clock_port, clock_period_ns, synth_top (default: module)
# Stages:
#   create  create_ip, set_property, read every CONFIG.* back (readback_config.tsv), generate_target all
#   sim     add the testbench to sim_1, launch_simulation (behavioural, xsim), run all, exit the simulator
#   synth   out-of-context synth_design of the IP, clock constraint, utilisation + timing reports (post-synthesis)
# Each stage writes <workdir>/<stage>.done on success. Errors stop the run (non-zero exit), the Python side reads the log.
set_param general.maxThreads 1
set_param synth.maxThreads 1
set cfgfile [lindex $argv 0]
set stages [lrange $argv 1 end]
source $cfgfile
set wd [file normalize $ipgen(workdir)]
file mkdir $wd
set m $ipgen(module)

proc stage_done {wd s} { set f [open $wd/$s.done w]; puts $f [clock format [clock seconds]]; close $f }
proc tsv_escape {v} { return [string map [list "\t" " " "\n" " "] $v] }

if {[lsearch $stages create] >= 0} {
    create_project -force proj $wd/proj -part $ipgen(part)
    file mkdir $wd/ip
    eval create_ip $ipgen(create_args) -module_name $m -dir $wd/ip
    set ip [get_ips $m]
    # all properties at once (some depend on each other: CoefficientSource COE_File needs Coefficient_File in the same
    # call); if the IP refuses, fall back to one at a time so the refused value names itself
    set perr {}
    if {[catch {set_property -dict $ipgen(props) $ip} e]} {
        lappend perr "all-at-once: $e"
        foreach {k v} $ipgen(props) {
            if {[catch {set_property $k $v $ip} e2]} { lappend perr "$k=$v: $e2" }
        }
    }
    set f [open $wd/set_errors.txt w]; foreach e $perr { puts $f $e }; close $f
    set f [open $wd/readback_config.tsv w]
    foreach p [lsort [list_property $ip]] {
        if {[string match CONFIG.* $p]} { puts $f "$p\t[tsv_escape [get_property $p $ip]]" }
    }
    close $f
    generate_target all $ip
    foreach pf [list $wd/ip/$m/$m.xci] { if {![file exists $pf]} { error "no xci at $pf" } }
    stage_done $wd create
}

if {[lsearch $stages sim] >= 0} {
    if {[lsearch $stages create] < 0} { open_project $wd/proj/proj.xpr }
    set fs [get_filesets sim_1]
    if {[llength [get_files -quiet -of_objects $fs [file normalize $ipgen(tb_file)]]] == 0} {
        add_files -fileset sim_1 -norecurse $ipgen(tb_file)
    }
    set_property top $ipgen(tb_top) $fs
    set_property top_lib xil_defaultlib $fs
    set_property -name {xsim.simulate.runtime} -value {0ns} -objects $fs
    launch_simulation -simset sim_1 -mode behavioral
    run all
    close_sim
    stage_done $wd sim
}

if {[lsearch $stages synth] >= 0} {
    # fresh in-memory session on the generated IP (no project): the flow's own non-project style
    close_project -quiet
    create_project -in_memory -part $ipgen(part)
    read_ip $wd/ip/$m/$m.xci
    set top $m
    if {[info exists ipgen(synth_top)]} { set top $ipgen(synth_top) }
    synth_design -top $top -part $ipgen(part) -mode out_of_context
    create_clock -period $ipgen(clock_period_ns) -name ipclk [get_ports $ipgen(clock_port)]
    report_utilization -file $wd/utilization.rpt
    report_utilization -hierarchical -file $wd/utilization_hier.rpt
    report_timing_summary -delay_type max -max_paths 5 -file $wd/timing_summary.rpt
    report_timing -delay_type max -max_paths 1 -file $wd/timing_path.rpt
    stage_done $wd synth
}
