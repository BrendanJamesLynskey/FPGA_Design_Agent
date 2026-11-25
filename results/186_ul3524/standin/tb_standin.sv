// Small test for GTF_COMMON_STANDIN: lock behaviour and output frequency = ref x N / M (UG576 Equation 2-3).
`timescale 1fs/1fs
module tb_standin;
  reg refclk = 0; reg rst = 1; reg pd = 0;
  wire out0, outref0, lock0, out1, outref1, lock1;
  // 161.1328125 MHz = 6205.8 ps
  always #3102900 refclk = ~refclk;
  GTF_COMMON_STANDIN #(.QPLL0_FBDIV(64), .QPLL0_REFCLK_DIV(1), .QPLL1_FBDIV(66), .QPLL1_REFCLK_DIV(1), .LOCK_REFCLKS(256)) dut (
    .GTREFCLK00(refclk), .QPLL0REFCLKSEL(3'b001), .QPLL0RESET(rst), .QPLL0PD(pd), .QPLL0LOCK(lock0), .QPLL0OUTCLK(out0), .QPLL0OUTREFCLK(outref0),
    .GTREFCLK10(refclk), .QPLL1REFCLKSEL(3'b001), .QPLL1RESET(rst), .QPLL1PD(pd), .QPLL1LOCK(lock1), .QPLL1OUTCLK(out1), .QPLL1OUTREFCLK(outref1),
    .DRPCLK(refclk), .DRPEN(1'b0));
  integer n0, n1; real t0, t1, tl, fo;
  integer fails = 0;
  initial begin
    #50000000 ;
    if (lock0 !== 0 || out0 !== 0) begin fails++; $display("FAIL: lock/out active while in reset"); end
    rst = 0; tl = $realtime;
    wait (lock0); $display("lock0 after %0.1f reference cycles", ($realtime - tl)/6205800.0);
    // count output edges over 1000 reference cycles
    n0 = 0; n1 = 0; t0 = $realtime;
    repeat (1000) @(posedge refclk);
    t1 = $realtime;
    $display("QPLL0: %0d output rising edges in %0.1f ref cycles; ratio %0.3f (expect 64)", n0, (t1-t0)/6205800.0, n0/((t1-t0)/6205800.0));
    $display("QPLL1: %0d output rising edges; ratio %0.3f (expect 66)", n1, n1/((t1-t0)/6205800.0));
    if (n0 < 63900 || n0 > 64100) begin fails++; $display("FAIL: QPLL0 ratio"); end
    if (n1 < 65900 || n1 > 66100) begin fails++; $display("FAIL: QPLL1 ratio"); end
    pd = 1; #20000000;
    if (lock0 !== 0 || out0 !== 0) begin fails++; $display("FAIL: power-down did not drop lock/clock"); end
    pd = 0; wait (lock0); $display("re-lock after power-down OK");
    if (fails == 0) $display("PASS: stand-in tests"); else $display("FAILED: %0d", fails);
    $finish;
  end
  always @(posedge out0) n0 = n0 + 1;
  always @(posedge out1) n1 = n1 + 1;
endmodule
