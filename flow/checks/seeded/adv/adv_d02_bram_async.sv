// adv_d02_bram_async: an attack design for the sign-off netlist scan (brief 71B)
module adv_d02_bram_async(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
logic [15:0] mem [0:255]; logic [15:0] rd, rq; logic ra; assign ra = ~rst_n_btn;
always_ff @(posedge clk_a) begin mem[a[7:0]] <= b; rd <= mem[b[7:0]]; end
always_ff @(posedge clk_a or posedge ra) if (ra) rq <= '0; else rq <= rd;
assign p = {16'd0, rq};
assign q = d;
endmodule
