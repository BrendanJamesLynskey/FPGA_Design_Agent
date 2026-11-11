# measure_u.tcl: the clock-uncertainty measurements U1-U7 (brief 20 part B) on io_u, xc7a100tcsg324-1, Vivado 2025.2.
#   vivado -mode batch -source measure_u.tcl -tclargs <flow dir> <fixture dir> <out dir>
# base: build with xdc/io_u.xdc and report the three path kinds (full period on clk200, half period on clk200, the
# clk100 -> clk200 crossing) with their uncertainty breakdown; then re-time the routed design with set_input_jitter
# (U2), set_system_jitter (U3) and each timing corner alone (U6); then build again from the synthesised netlist with a
# 0.5 ns implementation-only setup uncertainty on clk200 (U4), removed before routing.
set_param general.maxThreads 1
set_param synth.maxThreads 1
lassign $argv flow_dir fx_dir out
file mkdir $out
read_verilog -sv $fx_dir/rtl/io_u.sv
read_xdc $fx_dir/xdc/io_u.pins.xdc
read_xdc $fx_dir/xdc/io_u.xdc
synth_design -top io_u -part xc7a100tcsg324-1
write_checkpoint -force $out/post_synth.dcp
opt_design; place_design; phys_opt_design; route_design
write_checkpoint -force $out/post_route.dcp
source $flow_dir/io_paths.tcl
proc upaths {o} {
    file mkdir $o
    io_dump_paths $o/io_paths.txt
    report_timing_summary -max_paths 3 -file $o/timing_summary.rpt
    foreach {k dt} {setup max hold min} {
        report_timing -from [get_cells {a_reg[*] b_reg[*]}] -to [get_cells {s_reg[*]}] -delay_type $dt -max_paths 1 -file $o/full_period_$k.rpt
        report_timing -to [get_cells hq_reg] -delay_type $dt -max_paths 1 -file $o/half_period_$k.rpt
        report_timing -from [get_cells {slow_reg[*]}] -to [get_cells {x_reg[*]}] -delay_type $dt -max_paths 1 -file $o/crossing_$k.rpt
    }
    report_timing -delay_type max -max_paths 1 -file $o/timing_worst_setup.rpt
    report_timing -delay_type min -max_paths 1 -file $o/timing_worst_hold.rpt
    report_clocks -file $o/clocks.rpt
}
upaths $out/u1_base
puts "CLOCKS [join [get_clocks] { }]"
set c200 [get_clocks -of_objects [get_pins mmcm/CLKOUT0]]
set c100 [get_clocks -of_objects [get_pins mmcm/CLKOUT1]]
puts "C200 $c200 C100 $c100"
# U2: input jitter on the board clock (illustrative 100 ps: the Nexys A7 reference manual gives no oscillator jitter)
set_input_jitter [get_clocks sys_clk] 0.100
upaths $out/u2_input_jitter
# U3: system jitter changed from its default
reset_timing; read_xdc $fx_dir/xdc/io_u.xdc
set_system_jitter 0.100
upaths $out/u3_system_jitter
reset_timing; read_xdc $fx_dir/xdc/io_u.xdc
# U6: each corner alone
if {[catch {config_timing_corners -corner Fast -delay_type none} e]} { puts "CTC-ERR $e"; help config_timing_corners }
upaths $out/u6_slow_only
config_timing_corners -corner Fast -delay_type min_max
config_timing_corners -corner Slow -delay_type none
upaths $out/u6_fast_only
config_timing_corners -corner Slow -delay_type min_max
report_timing_summary -max_paths 3 -file $out/u6_restored_summary.rpt
# U4: an implementation-only setup margin of 0.5 ns on clk200, removed before routing (UG949 over-constraining)
close_design
open_checkpoint $out/post_synth.dcp
set c200 [get_clocks -of_objects [get_pins mmcm/CLKOUT0]]
set_clock_uncertainty -setup 0.500 $c200
opt_design; place_design; phys_opt_design
file mkdir $out/u4_margin
report_timing_summary -max_paths 3 -file $out/u4_margin/placed_with_margin.rpt
set_clock_uncertainty -setup 0.000 $c200
report_timing_summary -max_paths 3 -file $out/u4_margin/placed_margin_removed.rpt
route_design
upaths $out/u4_margin/signoff
set_clock_uncertainty -setup 0.500 $c200
report_timing_summary -max_paths 3 -file $out/u4_margin/routed_with_margin.rpt
puts "MEASURE-DONE io_u"
