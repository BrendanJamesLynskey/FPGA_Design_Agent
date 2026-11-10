# cmt_check_probe.tcl: run flow/cmt_check.tcl on hand-instantiated MMCMs, legal and illegal (brief 18, section 2b).
#   vivado -mode batch -source flow/cmt_check_probe.tcl -tclargs <part> <out dir> <name>:<D>:<M>:<O0> ...
# Also records what report_drc and report_methodology say about the same netlist (the KB claims: nothing).
set_param general.maxThreads 1
set_param synth.maxThreads 1
set part [lindex $argv 0]; set out [file normalize [lindex $argv 1]]; file mkdir $out
source [file join [file dirname [file normalize [info script]]] cmt_check.tcl]
foreach spec [lrange $argv 2 end] {
    lassign [split $spec :] name d m o
    set v $out/top_$name.v
    set f [open $v w]
    puts $f "module top_${name}(input clk, input din, output reg dout);
  wire fb, fbb, c0, c0b, lk;
  MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .DIVCLK_DIVIDE($d), .CLKFBOUT_MULT_F($m), .CLKOUT0_DIVIDE_F($o)) mm
    (.CLKIN1(clk), .CLKFBIN(fbb), .CLKFBOUT(fb), .CLKOUT0(c0), .LOCKED(lk), .PWRDWN(1'b0), .RST(1'b0));
  BUFG b1(.I(fb), .O(fbb));
  BUFG b2(.I(c0), .O(c0b));
  reg q = 0;
  always @(posedge c0b) begin q <= din; dout <= q; end
endmodule"
    close $f
    read_verilog $v
    synth_design -top top_${name} -part $part
    create_clock -period 10.0 [get_ports clk]
    cmt_check $out/cmt_$name.rpt
    report_drc -file $out/drc_$name.rpt
    report_methodology -file $out/methodology_$name.rpt
    close_design
}
