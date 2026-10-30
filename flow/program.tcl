# program.tcl: program one board over JTAG, selected by its cable serial number,
# into the FPGA's volatile configuration memory (SRAM) only.
#
#   vivado -mode batch -source flow/program.tcl -tclargs <serial> <file.bit> [file.ltx]
#
# Run it through flow/program.py (or flow/run_vivado.sh designs/<name> program),
# which looks the serial up in the local board file, applies the USB-power gate
# and the memory-safe Vivado settings.
#
# Rules it enforces:
# - The serial must match exactly one target (hw_server shows targets as
#   localhost:3121/xilinx_tcf/Digilent/<serial>); there is no "first target"
#   fallback. With no match it lists what it found and stops.
# - The chain must hold exactly one device, and it must be an xc7a100t.
# - Flash is never written: any flash-like request (a -flash/-cfgmem flag, an
#   .mcs/.bin/.prm file, or anything that is not a .bit) fails here, before
#   Vivado touches the hardware. Writing the board's QSPI flash needs the
#   owner's explicit yes and a different, reviewed script.
# The argument checks come first and use plain Tcl, so a tclsh test can show the
# refusal without Vivado or a board (flow/tests/test_hw_flow.py).

proc fda_refuse {msg} {
    puts "program.tcl: REFUSED: $msg"
    error "program.tcl: REFUSED: $msg"
}

proc fda_check_args {argv} {
    foreach a $argv {
        set l [string tolower $a]
        if {[string match -* $l] && [regexp {flash|cfgmem|qspi|spi|bpi|mcs|prom} $l]} {
            fda_refuse "'$a' asks to write configuration flash. This flow programs volatile SRAM only; flash writes need the owner's explicit yes and are not supported here."
        }
        if {[regexp {\.(mcs|bin|prm|hex)$} $l]} {
            fda_refuse "'$a' is a flash image. This flow programs volatile SRAM only (a .bit file); flash writes need the owner's explicit yes and are not supported here."
        }
        if {[string match -* $l]} {
            fda_refuse "unknown option '$a'"
        }
    }
    lassign $argv serial bit ltx
    if {[llength $argv] < 2 || [llength $argv] > 3 || $serial eq "" || $bit eq ""} {
        fda_refuse "usage: -tclargs <cable serial> <file.bit> \[file.ltx\]"
    }
    if {![string match -nocase *.bit $bit]} { fda_refuse "'$bit' is not a .bit file" }
    if {$ltx ne "" && ![string match -nocase *.ltx $ltx]} { fda_refuse "'$ltx' is not a .ltx file" }
    return [list $serial $bit $ltx]
}

lassign [fda_check_args $argv] serial bit ltx
if {![file isfile $bit]} { fda_refuse "no bitstream $bit" }
if {$ltx ne "" && ![file isfile $ltx]} { fda_refuse "no probes file $ltx" }

set_param general.maxThreads 1
open_hw_manager
connect_hw_server -url localhost:3121
set targets [get_hw_targets -quiet "*/Digilent/${serial}*"]
if {[llength $targets] != 1} {
    puts "program.tcl: targets found:"
    foreach t [get_hw_targets -quiet] { puts "  ...[string range [get_property UID $t] end-4 end]" }
    fda_refuse "expected exactly one target with the given serial, found [llength $targets]"
}
open_hw_target $targets
set devs [get_hw_devices -quiet]
if {[llength $devs] != 1} { fda_refuse "expected one device on the chain, found [llength $devs]: $devs" }
set dev [lindex $devs 0]
if {[get_property PART $dev] ne "xc7a100t"} {
    fda_refuse "device $dev is a [get_property PART $dev], expected xc7a100t"
}
current_hw_device $dev
refresh_hw_device -update_hw_probes false $dev
set_property PROGRAM.FILE $bit $dev
if {$ltx ne ""} {
    set_property PROBES.FILE $ltx $dev
    set_property FULL_PROBES.FILE $ltx $dev
} else {
    set_property PROBES.FILE {} $dev
    set_property FULL_PROBES.FILE {} $dev
}
set t0 [clock milliseconds]
program_hw_devices $dev
set ms [expr {[clock milliseconds] - $t0}]
refresh_hw_device $dev
set done ?
catch {set done [get_property REGISTER.CONFIG_STATUS.BIT14_DONE_PIN $dev]}
puts "FDA-PROGRAMMED device=$dev part=[get_property PART $dev] done_pin=$done program_ms=$ms ilas=[llength [get_hw_ilas -quiet -of_objects $dev]]"
close_hw_target
disconnect_hw_server
