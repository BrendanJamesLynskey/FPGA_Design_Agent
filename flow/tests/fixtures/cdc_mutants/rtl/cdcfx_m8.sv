// M8: the source domain's reset clears a destination datapath register directly, unqualified.
module cdcfx_m8 (input logic clk_a, input logic clk_b, input logic rq_in, input logic [7:0] d_in, output logic [7:0] q_out);
    logic rq = 1'b0;
    always_ff @(posedge clk_a) rq <= rq_in;
    logic [7:0] dd = '0, q = '0;
    always_ff @(posedge clk_b) dd <= d_in;
    always_ff @(posedge clk_b or posedge rq) if (rq) q <= '0; else q <= dd;
    assign q_out = q;
endmodule
