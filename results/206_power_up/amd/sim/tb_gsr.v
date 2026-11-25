// Brief 206 X13: does the post-synthesis netlist start at INIT after the configuration GSR pulse, and does a reset of the
// opposite sense then win? DUT = the funcsim netlist of x2_sreset0 or x4_aclr with INITV=1 (module name from the netlist).
`timescale 1ns/1ps
module tb;
  reg clk = 0, rst = 0; reg [7:0] d = 8'h5A; wire [7:0] q;
  `DUT dut (.clk(clk), .rst(rst), .d(d), .q(q));
  initial begin
    #50  $display("T050_during_GSR q=%h", q);
    #100 $display("T150_after_GSR_no_clock q=%h", q);
    rst = 1; #2 $display("T152_rst_high_no_edge q=%h", q);
    #3 clk = 1; #1 $display("T156_after_edge_with_rst q=%h", q); #4 clk = 0;
    rst = 0; #5 clk = 1; #1 $display("T166_after_edge_d q=%h", q);
    $finish;
  end
endmodule
