# licence_check.tcl (brief 33): can Vivado synthesise, place and route each of our parts with no licence at all?
# Run by licence_check.sh with HOME pointing at an empty directory (so ~/.Xilinx/Xilinx.lic is not found) and no
# licence variables. A tiny counter per part; the result per part (and Vivado's licence messages) goes to the log.
set_param general.maxThreads 1
set src [file join [pwd] licence_check_counter.sv]   ;# written in the empty working directory
set f [open $src w]
puts $f "module counter (input logic clk, input logic rst, output logic \[7:0\] q);"
puts $f "  always_ff @(posedge clk) q <= rst ? 8'd0 : q + 8'd1;"
puts $f "endmodule"
close $f
foreach part [expr {[info exists ::env(LC_PARTS)] ? $::env(LC_PARTS) : {xc7a100tcsg324-1 xc7z020clg400-1 xck26-sfvc784-2LV-c}}] {
    if {[catch {
        read_verilog -sv $src
        synth_design -top counter -part $part -mode out_of_context
        create_clock -period 10 [get_ports clk]
        opt_design
        place_design
        route_design
        puts "LICENCE-CHECK $part OK (synth, place, route)"
    } err]} {
        puts "LICENCE-CHECK $part FAILED: [string map {\n { }} $err]"
    }
    close_project -quiet
}
