// Latency check for the c13_hough_lines core variants (Icarus): 40 random points sent one after another; for each, the
// clocks `busy` stays high (the whole vote pipeline). Then every one of the 1,536 cells is read and a checksum printed,
// so a variant that changes the counts shows a different checksum. Run by run_latency.py.
`timescale 1ns/1ps
module tb;
  logic clk = 0, rst_n = 0, pt_valid = 0, clear = 0; logic [7:0] pt_x = 0, pt_y = 0; logic busy;
  logic [3:0] rd_theta = 0; logic [6:0] rd_rho = 0; logic [15:0] rd_cnt;
  hough #(.NT(16), .NR(96), .ROFF(48)) dut(.*);
  always #5 clk = ~clk;
  integer i, t, r, sum, seed, busyclk, maxb;
  initial begin
    seed = 7; sum = 0; maxb = 0;
    repeat (3) @(posedge clk); rst_n <= 1; @(posedge clk);
    clear <= 1; @(posedge clk); clear <= 0; @(posedge clk);
    for (i = 0; i < 40; i++) begin
      pt_x <= $random(seed); pt_y <= $random(seed); pt_valid <= 1; @(posedge clk); pt_valid <= 0;
      busyclk = 0; @(negedge clk);
      while (busy && busyclk < 4000) begin busyclk++; @(negedge clk); end
      if (busyclk > maxb) maxb = busyclk;
      @(posedge clk);
    end
    for (t = 0; t < 16; t++) for (r = 0; r < 96; r++) begin
      rd_theta <= t; rd_rho <= r; @(posedge clk); @(posedge clk); #1 sum = sum * 31 + rd_cnt;
    end
    $display("BUSY_CLOCKS_PER_POINT %0d CHECKSUM %0d", maxb, sum);
    $finish;
  end
endmodule
