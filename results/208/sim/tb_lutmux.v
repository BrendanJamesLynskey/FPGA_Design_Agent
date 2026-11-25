`timescale 1ps/1ps
// Brief 208 (c3): the RTL clock mux of designs/mux_lut.v, behaviourally: select changes at times unrelated to the clocks.
module tb_lutmux;
  reg clk0 = 0, clk1 = 0, sel = 0;
  always #5000 clk0 = ~clk0;
  always #6667 clk1 = ~clk1;
  wire clkm = sel ? clk1 : clk0;
  integer runts = 0; time t = 0;
  always @(clkm) begin if ($time - t < 4900 && $time > 1000) begin runts = runts + 1; $display("RUNT %0d ps at %0t", $time - t, $time); end t = $time; end
  integer k;
  initial begin
    #50000;
    for (k = 0; k < 40; k = k + 1) begin #(23011 + k * 997) sel = ~sel; end
    #50000 $display("SCEN c3_lut_mux switches=40 runts=%0d", runts);
    $finish;
  end
endmodule
