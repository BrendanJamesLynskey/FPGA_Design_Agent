# adv.tcl: synthesise the netlist-scan attack designs of brief 71B in ONE Vivado session and run the reset scan and AMD's
# reports on each (the same procs as the sign-off gate: flow/checks/vivado_checks.tcl).
#
#   vivado -mode batch -source flow/checks/seeded/adv/adv.tcl -tclargs <out_root> [case ...]
#
# Out-of-context synthesis for xc7a100tcsg324-1, two asynchronous clocks (as seeded.tcl). A case whose synthesis fails
# writes <out_root>/<case>/synth_failed.txt. The shell's reset_sync is read for every case but adv_a11 (which defines its own).
set ::fda_checks_lib 1
set here [file normalize [file dirname [info script]]]
set root [file normalize [file join $here .. .. .. ..]]
source [file join $root flow checks vivado_checks.tcl]
set_param general.maxThreads 1
set outroot [file normalize [lindex $argv 0]]
set cases [lrange $argv 1 end]
if {[llength $cases] == 0} {
    foreach f [lsort [glob -directory $here adv_*.sv]] { lappend cases [file rootname [file tail $f]] }
}
file mkdir $outroot
puts "FDA-VIVADO-VERSION [version -short]"
foreach c $cases {
    set out [file join $outroot $c]
    file mkdir $out
    puts "FDA-ADV $c"
    set files [list [file join $here $c.sv]]
    if {![string match adv_a11* $c]} { lappend files [file join $root shell rtl reset_sync.sv] }
    if {[catch {
        read_verilog -sv $files
        synth_design -top $c -part xc7a100tcsg324-1 -mode out_of_context
    } err]} {
        set f [open [file join $out synth_failed.txt] w]; puts $f $err; close $f
        catch {close_project}
        continue
    }
    create_clock -name clk_a -period 10.000 [get_ports clk_a]
    create_clock -name clk_b -period 7.000 [get_ports clk_b]
    set_clock_groups -asynchronous -group clk_a -group clk_b
    foreach r {methodology drc cdc reset_scan} { fda_report $r $out }
    close_project
}
puts "FDA-ADV-DONE"
