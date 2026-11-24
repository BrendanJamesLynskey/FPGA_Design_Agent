// Brief 208 (q1, q2): two clocks through Altera's clock control block (altclkctrl), select from a register.
module q_clkctrl #(parameter GF = "OFF") (
  input wire clk0, input wire clk1, input wire sel_in, output reg doutm, output reg dout0);
  reg sel_r = 1'b0;
  always @(posedge clk0) sel_r <= sel_in;
  wire clkm;
  altclkctrl #(.clock_type("Global Clock"), .number_of_clocks(2), .width_clkselect(1),
               .use_glitch_free_switch_over_implementation(GF))
    u_clkctrl (.inclk({clk1, clk0}), .clkselect(sel_r), .ena(1'b1), .outclk(clkm));
  reg [31:0] rm = 32'h1, r0 = 32'h1;
  always @(posedge clkm) rm <= {rm[30:0], rm[31] ^ rm[21] ^ rm[1] ^ rm[0]};
  always @(posedge clkm) doutm <= ^rm;
  always @(posedge clk0) r0 <= {r0[30:0], r0[31] ^ r0[21] ^ r0[1] ^ r0[0]};
  always @(posedge clk0) dout0 <= ^r0 ^ rm[0];       // one path from the muxed tree into clk0 (path C)
endmodule
