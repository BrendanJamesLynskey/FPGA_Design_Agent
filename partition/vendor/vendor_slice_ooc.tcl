# vendor_slice_ooc.tcl (brief 151, owner direction 2026-11-21: "measure the vendor convention first"): builds AMD's AXI Register Slice
# IP (axi_register_slice) in every register configuration its AW channel offers, out of context, and records LUT, FF and WNS at one
# clock, so that ip_lib/pipe_reg's modes can be compared with it on area and Fmax. NOT RUN YET (queued; Vivado). The allowed values of
# CONFIG.REG_AW are read from the tool (list_property_value), not assumed, because the names and numbers of the modes are
# the product guide's to state. Environment: PART, T_NS, OUT. Sibling: vendor_slice_tb.sv (xsim: latency, bubbles, throughput).
set part $::env(PART); set t_ns $::env(T_NS); set out $::env(OUT)
file mkdir $out
set_param general.maxThreads 1
create_project -in_memory -part $part
set probe [create_ip -name axi_register_slice -vendor xilinx.com -library ip -module_name vs_probe -dir $out/ip_probe]
set modes [list_property_value -object $probe CONFIG.REG_AW]
puts "REG_AW allowed values: $modes"
set fh [open $out/vendor_slice.json w]
puts $fh "\["
set first 1
foreach m $modes {
    set name vs_m$m
    set ip [create_ip -name axi_register_slice -vendor xilinx.com -library ip -module_name $name -dir $out/ip_$name]
    # the same mode on every channel, AXI4-Lite 32-bit so that the five channels are small
    set_property -dict [list CONFIG.PROTOCOL AXI4LITE CONFIG.REG_AW $m CONFIG.REG_W $m CONFIG.REG_B $m CONFIG.REG_AR $m CONFIG.REG_R $m] $ip
    generate_target all $ip
    synth_ip $ip
    set dcp [lindex [split [exec find $out/ip_$name -name $name.dcp] "\n"] 0]
    close_project -quiet
    open_checkpoint $dcp
    create_clock -name aclk -period $t_ns [get_ports aclk]
    set_input_delay 0 -clock aclk [get_ports -filter {DIRECTION == IN && NAME != aclk}]
    set_output_delay 0 -clock aclk [get_ports -filter {DIRECTION == OUT}]
    opt_design; place_design; route_design
    set wns [get_property SLACK [get_timing_paths -max_paths 1]]
    set util [report_utilization -return_string]
    regexp {CLB LUTs\s*\|\s*([0-9]+)} $util -> luts
    regexp {CLB Registers\s*\|\s*([0-9]+)} $util -> ffs
    if {!$first} { puts $fh "," }
    set first 0
    puts $fh "\{\"reg_config\": \"$m\", \"part\": \"$part\", \"t_ns\": $t_ns, \"wns_ns\": $wns, \"lut\": $luts, \"ff\": $ffs\}"
    close_design
    create_project -in_memory -part $part
}
puts $fh "\]"
close $fh
