# Brief 206: build one Quartus Prime Lite project for the power-up arms and compile it.
#   quartus_sh -t q_project.tcl <family-tag> <INITV 0|1> <pushback ON|OFF> <build-dir> <rtl-dir> <amd-rtl-dir>
# family-tag: c4 (EP4CE22F17C6), c5 (5CEBA4F23C7), m10 (10M50DAF484C7G). One run per case.
package require ::quartus::project
package require ::quartus::flow

set tag   [lindex $argv 0]
set initv [lindex $argv 1]
set pb    [lindex $argv 2]
set bdir  [lindex $argv 3]
set rtl   [lindex $argv 4]
set artl  [lindex $argv 5]
array set fam {c4 {"Cyclone IV E" EP4CE22F17C6} c5 {"Cyclone V" 5CEBA4F23C7} m10 {"MAX 10" 10M50DAF484C7G}}
set family [lindex $fam($tag) 0]
set device [lindex $fam($tag) 1]
set name "q_${tag}_i${initv}_pb${pb}"
file mkdir $bdir/$name
cd $bdir/$name
project_new $name -overwrite
set_global_assignment -name FAMILY $family
set_global_assignment -name DEVICE $device
set_global_assignment -name TOP_LEVEL_ENTITY q_top
set_global_assignment -name SYSTEMVERILOG_FILE $rtl/q_top.sv
set_global_assignment -name VHDL_FILE $artl/x12_vhdl_int.vhd
set_global_assignment -name SDC_FILE $rtl/../tcl/q.sdc
set_global_assignment -name NUM_PARALLEL_PROCESSORS 1
set_global_assignment -name NOT_GATE_PUSH_BACK $pb
set_global_assignment -name EDA_SIMULATION_TOOL "Questa Intel FPGA (Verilog)"
set_global_assignment -name EDA_OUTPUT_DATA_FORMAT "VERILOG HDL" -section_id eda_simulation
set_parameter -name INITV $initv
foreach p {rst d1 d2 d3 d4 q1 q2 q3 q4 ma mb mp rwe rwa rra rwd rq d7 d8 q7 q8 inc9 q9} {
  set_instance_assignment -name VIRTUAL_PIN ON -to "${p}*"
}
set_instance_assignment -name FAST_INPUT_REGISTER ON -to "io_din*"
set_instance_assignment -name FAST_OUTPUT_REGISTER ON -to "io_dout*"
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to "io_d*"
if {$tag eq "c5"} { set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to "clk*" }
export_assignments
if {[catch {execute_flow -compile} err]} { puts "### COMPILE FAILED: $err" }
if {[catch {execute_module -tool eda -args "--simulation --tool=questa_oem --format=verilog"} err]} { puts "### EDA FAILED: $err" }
project_close
