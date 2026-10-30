# program.tcl: program one board over JTAG, selected by its cable serial number.
#
#   vivado -mode batch -source flow/program.tcl -tclargs <serial> <file.bit> [file.ltx]
#
# The serial is the Digilent cable's (hw_server shows targets as
# localhost:3121/xilinx_tcf/Digilent/<serial>). There is no "first target"
# fallback: with no match it lists what it found and stops. It programs the
# FPGA's volatile configuration only; it never writes flash.
# (Written in F0A; first used on hardware in F0B.)

lassign $argv serial bit ltx
if {$serial eq "" || $bit eq ""} {
    error "usage: -tclargs <cable serial> <file.bit> \[file.ltx\]"
}
open_hw_manager
connect_hw_server -url localhost:3121
set targets [get_hw_targets -quiet "*/Digilent/${serial}*"]
if {[llength $targets] != 1} {
    puts "program.tcl: targets found:"
    foreach t [get_hw_targets -quiet] { puts "  $t" }
    error "program.tcl: expected exactly one target with serial '$serial', found [llength $targets]"
}
open_hw_target $targets
set dev [lindex [get_hw_devices -quiet xc7a100t_*] 0]
if {$dev eq ""} { error "program.tcl: no xc7a100t on target $targets" }
current_hw_device $dev
set_property PROGRAM.FILE $bit $dev
if {$ltx ne ""} { set_property PROBES.FILE $ltx $dev; set_property FULL_PROBES.FILE $ltx $dev }
program_hw_devices $dev
refresh_hw_device $dev
puts "program.tcl: programmed $dev on $targets with $bit"
close_hw_target
disconnect_hw_server
