# mmcm_timing_probe.tcl: does the timer see an MMCM's jitter and phase error without the Clocking Wizard? (brief 18, 2b)
#   vivado -mode batch -source flow/mmcm_timing_probe.tcl -tclargs <part> <out dir> <name>:<D>:<M>:<O0> ...
# Builds a tiny RTL top (100 MHz in -> MMCME2_BASE -> BUFG -> two flip-flops), synthesises it and reads the clock
# uncertainty report_timing gives on the MMCM-clocked path (TSJ / DJ / PE). Writes <out dir>/mmcm_timing.jsonl.
set_param general.maxThreads 1
set_param synth.maxThreads 1
set part [lindex $argv 0]; set out [file normalize [lindex $argv 1]]
file mkdir $out
set jf [open $out/mmcm_timing.jsonl w]
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
    synth_design -top top_$name -part $part
    create_clock -period 10.0 [get_ports clk]
    set rpt [report_timing -from [get_cells q_reg] -to [get_cells dout_reg] -return_string]
    set unc ""; set tsj ""; set dj ""; set pe ""; set tij ""
    regexp {Clock Uncertainty:\s+([0-9.]+)ns} $rpt -> unc
    regexp {Total System Jitter\s+\(TSJ\):\s+([0-9.]+)ns} $rpt -> tsj
    regexp {Total Input Jitter\s+\(TIJ\):\s+([0-9.]+)ns} $rpt -> tij
    regexp {Discrete Jitter\s+\(DJ\):\s+([0-9.]+)ns} $rpt -> dj
    regexp {Phase Error\s+\(PE\):\s+([0-9.]+)ns} $rpt -> pe
    set fh [open $out/timing_$name.rpt w]; puts $fh $rpt; close $fh
    puts $jf "{\"name\": \"$name\", \"D\": $d, \"M\": $m, \"O0\": $o, \"uncertainty_ns\": \"$unc\", \"TSJ_ns\": \"$tsj\", \"TIJ_ns\": \"$tij\", \"DJ_ns\": \"$dj\", \"PE_ns\": \"$pe\"}"
    flush $jf
    close_design
}
close $jf
