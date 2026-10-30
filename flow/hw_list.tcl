# hw_list.tcl: list every JTAG target on the local hw_server and the devices on
# each chain, one machine-readable line each (flow/hw_discover.py parses them).
#
#   vivado -mode batch -source flow/hw_list.tcl
#
#   FDA-TARGET <uid> <name>
#   FDA-DEVICE <uid> <device> <part> <idcode>
# Read-only: it opens each target to scan its chain and programs nothing.

set_param general.maxThreads 1
open_hw_manager
connect_hw_server -url localhost:3121
foreach t [get_hw_targets -quiet] {
    puts "FDA-TARGET [get_property UID $t] $t"
    if {[catch {open_hw_target $t} msg]} {
        puts "FDA-TARGET-ERROR [get_property UID $t] $msg"
        continue
    }
    foreach d [get_hw_devices -quiet] {
        puts "FDA-DEVICE [get_property UID $t] $d [get_property PART $d] [get_property IDCODE_HEX $d]"
    }
    close_hw_target $t
}
puts "FDA-LIST-DONE"
disconnect_hw_server
