// C12: a reset request from clk_a released into clk_b through a 2-flop asynchronous-assert, synchronous-release bridge.
module cdcfx_c12 (input logic clk_a, input logic clk_b, input logic rq_in, output logic [7:0] q_out);
    logic rq = 1'b0;
    always_ff @(posedge clk_a) rq <= rq_in;
    (* ASYNC_REG = "TRUE" *) logic [1:0] br = 2'b11;
    always_ff @(posedge clk_b or posedge rq)
        if (rq) br <= 2'b11; else br <= {br[0], 1'b0};
    logic [7:0] q = '0;
    always_ff @(posedge clk_b) if (br[1]) q <= '0; else q <= q + 1'b1;
    assign q_out = q;
endmodule
