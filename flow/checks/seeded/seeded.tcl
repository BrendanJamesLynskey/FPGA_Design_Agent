# seeded.tcl: synthesise the reset check's seeded designs in ONE Vivado session and run the check suite's Vivado
# reports on each (brief 71). Also writes the release's methodology and DRC rule catalogue once.
#
#   vivado -mode batch -source flow/checks/seeded/seeded.tcl -tclargs <out_root> [case ...]
#
# Out-of-context synthesis for xc7a100tcsg324-1 (the Nexys A7 part), two asynchronous clocks. A case whose synthesis
# fails writes <out_root>/<case>/synth_failed.txt: a mutant that does not compile is not "caught".
set ::fda_checks_lib 1
set here [file normalize [file dirname [info script]]]
set root [file normalize [file join $here .. .. ..]]
source [file join $here .. vivado_checks.tcl]
set_param general.maxThreads 1
set outroot [file normalize [lindex $argv 0]]
set cases [lrange $argv 1 end]
if {[llength $cases] == 0} {
    set cases {rst_clean rst_f1_async rst_f2_polarity rst_f3_dsp_async rst_f3b_bram_async rst_f4_cdc_sync rst_f4b_cdc_async rst_f5_lut_async}
}
file mkdir $outroot
set first 1
foreach c $cases {
    set out [file join $outroot $c]
    file mkdir $out
    puts "FDA-SEEDED $c"
    if {[catch {
        read_verilog -sv [list [file join $here $c.sv] [file join $root shell rtl reset_sync.sv]]
        synth_design -top $c -part xc7a100tcsg324-1 -mode out_of_context -include_dirs [list $here]
    } err]} {
        set f [open [file join $out synth_failed.txt] w]; puts $f $err; close $f
        catch {close_project}
        continue
    }
    create_clock -name clk_a -period 10.000 [get_ports clk_a]
    create_clock -name clk_b -period 7.000 [get_ports clk_b]
    set_clock_groups -asynchronous -group clk_a -group clk_b
    if {$first} { fda_report rule_catalogue $outroot; set first 0 }
    foreach r {methodology drc cdc control_sets reset_scan utilization} { fda_report $r $out }
    close_project
}
puts "FDA-SEEDED-DONE"
