// M10: the clk_a reset request drives the asynchronous clear of clk_b flops directly (release not synchronised).
module cdcfx_m10 (input logic clk_a, input logic clk_b, input logic rq_in, output logic [7:0] q_out);
    logic rq = 1'b0;
    always_ff @(posedge clk_a) rq <= rq_in;
    logic [7:0] q = '0;
    always_ff @(posedge clk_b or posedge rq) if (rq) q <= '0; else q <= q + 1'b1;
    assign q_out = q;
endmodule
