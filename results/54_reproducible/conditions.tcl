# conditions.tcl: the operating conditions of the attached 7-series device over JTAG, read-only, at the end
# of a board run (flow/program.tcl logs the same lines at programming time).
#   vivado -mode batch -source results/54_reproducible/conditions.tcl -tclargs <cable serial>
# Prints FDA-COND NOW/MAX/MIN lines (XADC status registers; MAX 0x20-0x23 and MIN 0x24-0x27 are latched in hardware
# since the last configuration) and FDA-COND FLAGS (0x3F). Conversions from UG480. Programs nothing, writes nothing.
lassign $argv serial
if {$serial eq ""} { error "conditions.tcl: usage: -tclargs <cable serial>" }
set_param general.maxThreads 1
open_hw_manager
connect_hw_server -url localhost:3121
set targets [get_hw_targets -quiet "*/Digilent/${serial}*"]
if {[llength $targets] != 1} { error "conditions.tcl: expected exactly one target with the given serial, found [llength $targets]" }
open_hw_target $targets
set dev [lindex [get_hw_devices] 0]
current_hw_device $dev
refresh_hw_device -update_hw_probes false $dev
set sm [get_hw_sysmons -of_objects $dev]
proc fda_code {sm addr} { return [expr {([scan [get_hw_sysmon_reg $sm $addr] %x] >> 4) & 0xFFF}] }
proc fda_t {c} { return [format %.2f [expr {$c * 503.975 / 4096.0 - 273.15}]] }
proc fda_v {c} { return [format %.4f [expr {$c * 3.0 / 4096.0}]] }
refresh_hw_sysmon $sm
puts "FDA-COND NOW TEMPERATURE=[get_property TEMPERATURE $sm] VCCINT=[get_property VCCINT $sm] VCCAUX=[get_property VCCAUX $sm] VCCBRAM=[get_property VCCBRAM $sm]"
puts "FDA-COND MAX TEMPERATURE=[fda_t [fda_code $sm 0x20]] VCCINT=[fda_v [fda_code $sm 0x21]] VCCAUX=[fda_v [fda_code $sm 0x22]] VCCBRAM=[fda_v [fda_code $sm 0x23]]"
puts "FDA-COND MIN TEMPERATURE=[fda_t [fda_code $sm 0x24]] VCCINT=[fda_v [fda_code $sm 0x25]] VCCAUX=[fda_v [fda_code $sm 0x26]] VCCBRAM=[fda_v [fda_code $sm 0x27]]"
puts "FDA-COND FLAGS [get_hw_sysmon_reg $sm 0x3F]"
puts "FDA-USR-ACCESS [get_property REGISTER.USR_ACCESS $dev]"
close_hw_target
disconnect_hw_server
