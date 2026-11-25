// Brief 208 (c): an RTL clock mux, written as a plain conditional assignment (a LUT, not a clock buffer).
//   TIED=1: the select is a constant (the counter-case: a mux that never switches).
module mux_lut #(parameter TIED = 0) (
  input  wire clk0, input wire clk1, input wire sel_in,
  output reg  doutm, output reg dout0);
  reg sel_r = 1'b0;
  always @(posedge clk0) sel_r <= sel_in;
  wire sel = TIED ? 1'b0 : sel_r;
  wire clkm = sel ? clk1 : clk0;
  reg [31:0] rm = 32'h1, r0 = 32'h1;
  always @(posedge clkm) rm <= {rm[30:0], rm[31] ^ rm[21] ^ rm[1] ^ rm[0]};
  always @(posedge clkm) doutm <= ^rm;
  always @(posedge clk0) r0 <= {r0[30:0], r0[31] ^ r0[21] ^ r0[1] ^ r0[0]};
  always @(posedge clk0) dout0 <= ^r0;
endmodule
