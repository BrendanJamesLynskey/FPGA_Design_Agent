# run_xsim.tcl (brief 56A): the GT Wizard loopback bench in xsim, project mode (the IP simulation models need xsim).
#   vivado -mode batch -source designs/b56a_gth_serdes/sim/run_xsim.tcl -tclargs <work dir>      (see run_xsim.sh)
# The GT Wizard core is created by the board build's own Tcl (ip/amd_ip.tcl), so the simulated core is the one that is built.
set wd [file normalize [lindex $argv 0]]
set root [file normalize [file join [file dirname [info script]] .. .. ..]]
set dsn $root/designs/b56a_gth_serdes
set tb_file $dsn/sim/tb_gth_loopback.sv
set tb_top tb_gth_loopback
set runtime "4 ms"
if {[info exists ::env(SIM_TB)]} { set tb_file $::env(SIM_TB); set tb_top $::env(SIM_TOP); set runtime $::env(SIM_RUN) }
file mkdir $wd
set part xck26-sfvc784-2LV-c
set out $wd
create_project -force sim $wd/proj -part $part
set_property XPM_LIBRARIES {XPM_CDC} [current_project]
proc set_part {args} {}      ;# the in-memory flow sets the part with set_part; a project already has it
source $dsn/ip/amd_ip.tcl
generate_target simulation [get_ips gth_wiz]
add_files -fileset sources_1 -norecurse [list $dsn/rtl/prbs64.sv $dsn/rtl/gth_serdes_core.sv]
add_files -fileset sim_1 -norecurse $tb_file
set_property file_type SystemVerilog [get_files *.sv]
set_property top $tb_top [get_filesets sim_1]
set_property top_lib xil_defaultlib [get_filesets sim_1]
update_compile_order -fileset sim_1
set_property -name {xsim.simulate.runtime} -value {0ns} -objects [get_filesets sim_1]
set_property -name {xsim.simulate.log_all_signals} -value {false} -objects [get_filesets sim_1]
launch_simulation -simset sim_1 -mode behavioral
run $runtime
close_sim
puts "XSIM-DONE"
