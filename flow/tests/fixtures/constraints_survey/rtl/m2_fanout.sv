// M2 (brief 105): one register controls the clock enable of NF flops (a high-fanout net). MODE selects the attribute on that register:
// 0 none, 1 MAX_FANOUT = 100, 2 MAX_FANOUT = 100 plus DONT_TOUCH, 3 DONT_TOUCH only.
module m2_fanout #(parameter int MODE = 0, parameter int NF = 3000) (
    input logic clk, input logic go_in, input logic [NF-1:0] d_in, output logic [NF-1:0] q_out);
    if (MODE == 0) begin : g0
        logic go = 1'b0;
        always_ff @(posedge clk) go <= go_in;
        always_ff @(posedge clk) if (go) q_out <= d_in;
    end else if (MODE == 1) begin : g1
        (* MAX_FANOUT = 100 *) logic go = 1'b0;
        always_ff @(posedge clk) go <= go_in;
        always_ff @(posedge clk) if (go) q_out <= d_in;
    end else if (MODE == 2) begin : g2
        (* MAX_FANOUT = 100, DONT_TOUCH = "TRUE" *) logic go = 1'b0;
        always_ff @(posedge clk) go <= go_in;
        always_ff @(posedge clk) if (go) q_out <= d_in;
    end else begin : g3
        (* DONT_TOUCH = "TRUE" *) logic go = 1'b0;
        always_ff @(posedge clk) go <= go_in;
        always_ff @(posedge clk) if (go) q_out <= d_in;
    end
endmodule
