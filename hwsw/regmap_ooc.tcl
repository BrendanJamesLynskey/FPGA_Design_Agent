# regmap_ooc.tcl: out-of-context build of one generated register block, to measure what a register-map setting costs
# (brief 64A2: unmapped OKAY against SLVERR). Same flow for every run:
#   vivado -mode batch -source hwsw/regmap_ooc.tcl -tclargs <run dir> <part> <period_ns> <top>
# The run dir holds the block's <top>.sv. Reports and summary.txt go to <run dir>/vivado/. The clock constraint is read
# before synth_design, so synthesis is timing driven. One thread.
set_param general.maxThreads 1
set_param synth.maxThreads 1
set_param chipscope.maxJobs 1
lassign $argv rd part period top
set out $rd/vivado
file mkdir $out
cd $rd
set fh [open $out/clock.xdc w]
puts $fh "create_clock -name aclk -period $period \[get_ports aclk\]"
close $fh
read_verilog -sv $top.sv
read_xdc -mode out_of_context $out/clock.xdc
synth_design -top $top -part $part -mode out_of_context
opt_design
place_design
route_design
report_utilization -file $out/utilization.rpt
report_timing_summary -max_paths 5 -file $out/timing_summary.rpt
set wns [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
set fh [open $out/summary.txt w]
puts $fh "part $part"
puts $fh "clock_period_ns $period"
puts $fh "wns_ns $wns"
close $fh
puts "regmap_ooc: done"
