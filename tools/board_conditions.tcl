# board_conditions.tcl (brief 55): the operating conditions of the attached 7-series device over JTAG, read-only.
#   vivado -mode batch -source tools/board_conditions.tcl -tclargs <cable serial>
#   FDA-COND NOW TEMPERATURE=<degC> VCCINT=<V> VCCAUX=<V> VCCBRAM=<V>
#   FDA-COND MAX TEMPERATURE=... VCCINT=... VCCAUX=... VCCBRAM=...     (XADC max registers 0x20-0x23: latched in hardware
#   FDA-COND MIN TEMPERATURE=... VCCINT=... VCCAUX=... VCCBRAM=...      since the last configuration; min registers 0x24-0x27)
#   FDA-COND FLAGS 0x....                                              (flag register 0x3F)
# Programs nothing and writes no register. The serial must match exactly one target. Conversions: UG480 (7-series XADC):
# 12-bit codes in bits 15:4; temperature = code * 503.975 / 4096 - 273.15; supply = code / 4096 * 3 V.
lassign $argv serial
if {$serial eq ""} { error "board_conditions.tcl: usage: -tclargs <cable serial>" }
set_param general.maxThreads 1
open_hw_manager
connect_hw_server -url localhost:3121
set targets [get_hw_targets -quiet "*/Digilent/${serial}*"]
if {[llength $targets] != 1} { error "board_conditions.tcl: expected exactly one target with the given serial, found [llength $targets]" }
open_hw_target $targets
set dev [lindex [get_hw_devices] 0]
current_hw_device $dev
set sm [get_hw_sysmons -of_objects $dev]
refresh_hw_sysmon $sm
puts "FDA-COND NOW TEMPERATURE=[get_property TEMPERATURE $sm] VCCINT=[get_property VCCINT $sm] VCCAUX=[get_property VCCAUX $sm] VCCBRAM=[get_property VCCBRAM $sm]"
proc code {sm addr} { return [expr {([scan [get_hw_sysmon_reg $sm $addr] %x] >> 4) & 0xFFF}] }
proc t {c} { return [format %.2f [expr {$c * 503.975 / 4096.0 - 273.15}]] }
proc v {c} { return [format %.4f [expr {$c * 3.0 / 4096.0}]] }
puts "FDA-COND MAX TEMPERATURE=[t [code $sm 0x20]] VCCINT=[v [code $sm 0x21]] VCCAUX=[v [code $sm 0x22]] VCCBRAM=[v [code $sm 0x23]]"
puts "FDA-COND MIN TEMPERATURE=[t [code $sm 0x24]] VCCINT=[v [code $sm 0x25]] VCCAUX=[v [code $sm 0x26]] VCCBRAM=[v [code $sm 0x27]]"
puts "FDA-COND FLAGS [get_hw_sysmon_reg $sm 0x3F]"
close_hw_target
disconnect_hw_server
