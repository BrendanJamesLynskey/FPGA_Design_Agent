# driver_cells.tcl: for each output port, the cell type driving the pad's buffer (brief 24 drills).
#   vivado -mode batch -source driver_cells.tcl -tclargs <checkpoint.dcp> <out file> <port> ...
# One line per port: "<port> <REF_NAME> <site> <number of nets in the cone of logic between the last flip-flop and the pin>".
lassign $argv dcp out
open_checkpoint $dcp
set f [open $out w]
foreach p [lrange $argv 2 end] {
    set pad [get_ports $p]
    set obuf [get_cells -of [get_nets -of $pad]]
    set drv [get_cells -of [get_pins -leaf -of [get_nets -of [get_pins [get_property NAME $obuf]/I]] -filter {DIRECTION == OUT}]]
    puts $f "$p [get_property REF_NAME $drv] [get_property SITE $drv]"
}
close $f
exit 0
