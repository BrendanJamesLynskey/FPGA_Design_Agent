// adv_b01_polarity: an attack design for the sign-off netlist scan (brief 71B)
module adv_b01_polarity(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
logic [7:0] r1, r2;
always_ff @(posedge clk_a) if (!rst_n_btn) r1 <= '0; else r1 <= {r1[6:0], d};
always_ff @(posedge clk_a) if (rst_n_btn) r2 <= '0; else r2 <= {r2[6:0], ~d};
assign q = r1[7] ^ r2[7];
assign p = '0;
endmodule
