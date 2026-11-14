// adv_z03_clean_two_domains: an attack design for the sign-off netlist scan (brief 71B)
module adv_z03_clean_two_domains(input logic clk_a, input logic clk_b, input logic rst_n_btn, input logic d, input logic [15:0] a, input logic [15:0] b, output logic q, output logic [31:0] p);
logic ra, rb;
reset_sync ua (.clk(clk_a), .rst_n_async(rst_n_btn), .rst(ra));
reset_sync ub (.clk(clk_b), .rst_n_async(rst_n_btn), .rst(rb));
logic qa, qb;
always_ff @(posedge clk_a) if (ra) qa <= 1'b0; else qa <= d;
always_ff @(posedge clk_b) if (rb) qb <= 1'b0; else qb <= d;
assign q = qa ^ qb;
assign p = '0;
endmodule
