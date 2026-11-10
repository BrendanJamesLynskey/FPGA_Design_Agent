# synth_fixture.tcl: synthesis only of one CDC fixture, then the post-synthesis CDC reports the gate reads
# (flow/build.tcl's post_synth block: AMD's XPM exceptions by cell name, report_cdc -details, and flow/cdc_paths.tcl).
#   vivado -mode batch -source synth_fixture.tcl -tclargs <flow dir> <fixture dir> <fixture name> <out dir>
set_param general.maxThreads 1
set_param synth.maxThreads 1
lassign $argv flow_dir fx_dir name out
file mkdir $out
read_verilog -sv $fx_dir/rtl/$name.sv
read_xdc $fx_dir/xdc/common.xdc
if {[file exists $fx_dir/xdc/$name.xdc]} { read_xdc -unmanaged $fx_dir/xdc/$name.xdc }
synth_design -top $name -part xc7a100tcsg324-1 -mode out_of_context
source $flow_dir/xpm_cdc.tcl
apply_xpm_cdc_constraints
report_cdc -details -file $out/cdc_synth.rpt
if {[file exists $flow_dir/cdc_paths.tcl]} {
    source $flow_dir/cdc_paths.tcl
    set t0 [clock milliseconds]
    cdc_dump_paths $out/cdc_paths_synth.rpt
    puts "CDC-PATHS-SECONDS [expr {([clock milliseconds] - $t0) / 1000.0}]"
}
