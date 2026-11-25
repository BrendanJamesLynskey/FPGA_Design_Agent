// Brief 208 (f): the same 512 registers clocked through a BUFGCE (MODE=0) or through a BUFG with a fabric clock
// enable (MODE=1). en_r is the enable in both cases; its activity is set in Tcl for the vectorless power estimate.
module pwr #(parameter MODE = 0, parameter W = 512) (
  input wire clk, input wire en_in, input wire din, output reg dout);
  wire clkb;
  BUFG u_bufg (.I(clk), .O(clkb));
  reg en_r = 1'b0;
  always @(posedge clkb) en_r <= en_in;
  reg [W-1:0] r = {W{1'b0}};
  generate if (MODE == 0) begin : g_bufgce
    wire gclk;
    BUFGCE u_bufgce (.I(clk), .CE(en_r), .O(gclk));
    always @(posedge gclk) r <= {r[W-2:0], r[W-1] ^ din};
  end else begin : g_fabce
    always @(posedge clkb) if (en_r) r <= {r[W-2:0], r[W-1] ^ din};
  end endgenerate
  always @(posedge clkb) dout <= ^r;
endmodule
