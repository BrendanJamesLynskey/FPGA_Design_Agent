# bd_export_probe.tcl (interop check only): can this Vivado install make a small IP Integrator block design
# and export it with write_bd_tcl and write_bd_layout? Writes <out>/probe.json with each step's result and whether each
# file was written (write_bd_layout only warns when it cannot draw). Run it twice: in batch mode, and in GUI mode on a
# virtual display (xvfb-run), which write_bd_layout needs:
#   vivado -mode batch -source flow/blockdesign/vivado/bd_export_probe.tcl -tclargs <out dir> batch
#   xvfb-run -a vivado -mode gui -source flow/blockdesign/vivado/bd_export_probe.tcl -tclargs <out dir> gui
# A third argument, noregen, leaves out regenerate_bd_layout (to see whether write_bd_layout needs it); the record is
# then probe_<mode>_noregen.json and the files probe_*_<mode>_noregen.*.
set out [lindex $argv 0]
set mode [lindex $argv 1]
set regen [expr {[lindex $argv 2] ne "noregen"}]
if {!$regen} { set mode "${mode}_noregen" }
file mkdir $out
set_param general.maxThreads 1
set res {}
proc step {name script} {
    upvar res res
    if {[catch {uplevel 1 $script} msg]} {
        lappend res "\"$name\": {\"ok\": false, \"msg\": \"[string map {\" ' \n { } \\ /} $msg]\"}"
        return 0
    }
    lappend res "\"$name\": {\"ok\": true}"
    return 1
}
step create_project { create_project -in_memory -part xc7a100tcsg324-1 }
step create_bd_design { create_bd_design probe }
step add_cells {
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 gpio0
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 gpio1
    create_bd_cell -type ip -vlnv xilinx.com:ip:axi_crossbar:2.1 xbar
    set_property -dict [list CONFIG.NUM_MI {2} CONFIG.NUM_SI {1} CONFIG.PROTOCOL {AXI4LITE}] [get_bd_cells xbar]
    make_bd_intf_pins_external [get_bd_intf_pins xbar/S00_AXI]
    create_bd_port -dir I -type clk -freq_hz 100000000 aclk
    create_bd_port -dir I -type rst aresetn
    set_property CONFIG.ASSOCIATED_BUSIF {S00_AXI_0} [get_bd_ports aclk]
    connect_bd_net [get_bd_ports aclk] [get_bd_pins xbar/aclk] [get_bd_pins gpio0/s_axi_aclk] [get_bd_pins gpio1/s_axi_aclk]
    connect_bd_net [get_bd_ports aresetn] [get_bd_pins xbar/aresetn] [get_bd_pins gpio0/s_axi_aresetn] [get_bd_pins gpio1/s_axi_aresetn]
    connect_bd_intf_net [get_bd_intf_pins xbar/M00_AXI] [get_bd_intf_pins gpio0/S_AXI]
    connect_bd_intf_net [get_bd_intf_pins xbar/M01_AXI] [get_bd_intf_pins gpio1/S_AXI]
}
step assign_address { assign_bd_address }
step validate_bd_design { validate_bd_design }
step write_bd_tcl { write_bd_tcl -force $out/probe_bd_$mode.tcl }
if {$regen} { step regenerate_bd_layout { regenerate_bd_layout } }
step write_bd_layout_svg { write_bd_layout -force -format svg $out/probe_layout_$mode.svg }
step write_bd_layout_pdf { write_bd_layout -force -format pdf $out/probe_layout_$mode.pdf }
set files {}
foreach f [list probe_bd_$mode.tcl probe_layout_$mode.svg probe_layout_$mode.pdf] {
    lappend files "\"$f\": [expr {[file exists $out/$f] ? [file size $out/$f] : -1}]"
}
set f [open $out/probe_$mode.json w]
puts $f "\{\"tool\": \"[version -short]\", \"mode\": \"$mode\", \"steps\": \{[join $res {, }]\}, \"file_bytes\": \{[join $files {, }]\}\}"
close $f
if {[string match gui* $mode]} { exit }
