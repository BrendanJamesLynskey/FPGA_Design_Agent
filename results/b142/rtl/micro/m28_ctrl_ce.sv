// m28_ctrl_ce: 64 registers with a clock enable and a synchronous reset (control-set use of CE and SR).
module m28_ctrl_ce (input logic clk, input logic ce, rst, input logic [63:0] d, output logic [63:0] q);
    logic cq, rq;
    always_ff @(posedge clk) begin cq <= ce; rq <= rst; if (rq) q <= '0; else if (cq) q <= d; end
endmodule
