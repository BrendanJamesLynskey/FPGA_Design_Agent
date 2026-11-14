// adv_c01_lut_drives_async: an attack design for the sign-off netlist scan (brief 71B)
module adv_c01_lut_drives_async(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
logic s1, s2, ar;
always_ff @(posedge clk_a) begin s1 <= d; s2 <= s1; end
assign ar = s1 & s2;
logic r;
always_ff @(posedge clk_a or posedge ar) if (ar) r <= 1'b0; else r <= d;
assign q = r;
assign p = '0;
endmodule
