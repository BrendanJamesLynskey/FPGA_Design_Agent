// adv_d01_dsp_async: an attack design for the sign-off netlist scan (brief 71B)
module adv_d01_dsp_async(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
logic signed [15:0] ar, br; logic signed [31:0] m;
logic ra; assign ra = ~rst_n_btn;
always_ff @(posedge clk_a or posedge ra) if (ra) begin ar <= '0; br <= '0; m <= '0; end else begin ar <= a; br <= b; m <= ar * br; end
assign p = m;
assign q = d;
endmodule
