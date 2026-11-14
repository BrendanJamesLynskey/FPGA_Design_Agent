// adv_c02_cdc_sync_reset: an attack design for the sign-off netlist scan (brief 71B)
module adv_c02_cdc_sync_reset(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
logic ra;
always_ff @(posedge clk_a) ra <= ~rst_n_btn;
logic [7:0] r;
always_ff @(posedge clk_b) if (ra) r <= '0; else r <= {r[6:0], d};
assign q = r[7];
assign p = '0;
endmodule
