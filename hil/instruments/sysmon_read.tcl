# sysmon_read.tcl: read the die sensors through the JTAG path (the hardware manager's SYSMON view of the XADC).
#   vivado -mode batch -source hil/instruments/sysmon_read.tcl -tclargs <cable serial>
#   FDA-SYSMON TEMPERATURE=<degC> VCCINT=<V> VCCAUX=<V> VCCBRAM=<V>
# Read-only: it programs nothing. The serial must match exactly one target (no "first target").
lassign $argv serial
if {$serial eq ""} { error "sysmon_read.tcl: usage: -tclargs <cable serial>" }
set_param general.maxThreads 1
open_hw_manager
connect_hw_server -url localhost:3121
set targets [get_hw_targets -quiet "*/Digilent/${serial}*"]
if {[llength $targets] != 1} { error "sysmon_read.tcl: expected exactly one target with the given serial, found [llength $targets]" }
open_hw_target $targets
set dev [lindex [get_hw_devices] 0]
current_hw_device $dev
set sm [get_hw_sysmons -of_objects $dev]
refresh_hw_sysmon $sm
puts "FDA-SYSMON TEMPERATURE=[get_property TEMPERATURE $sm] VCCINT=[get_property VCCINT $sm] VCCAUX=[get_property VCCAUX $sm] VCCBRAM=[get_property VCCBRAM $sm]"
close_hw_target
disconnect_hw_server
