// m29_ctrl_sets: four groups of 16 registers with different enable and reset (four control sets), plus a set-to-one reset group.
module m29_ctrl_sets (input logic clk, input logic [3:0] ce, rst, input logic [15:0] d [4], output logic [15:0] q [4]);
    logic [3:0] cq, rq;
    always_ff @(posedge clk) begin
        cq <= ce; rq <= rst;
        for (int i = 0; i < 3; i++) begin if (rq[i]) q[i] <= '0; else if (cq[i]) q[i] <= d[i]; end
        if (rq[3]) q[3] <= '1; else if (cq[3]) q[3] <= d[3];
    end
endmodule
