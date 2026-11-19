// M1 (brief 105): 24 independent single-bit synchronisers from clk_a to clk_b, with and without ASYNC_REG, surrounded by logic so the
// placer has a reason to move the chain's flops apart. AREG = 1: (* ASYNC_REG = "TRUE" *) on both stages; AREG = 0: the same two flops, no attribute.
module m1_sync #(parameter int AREG = 1, parameter int N = 24) (
    input  logic clk_a, input logic clk_b,
    input  logic [N-1:0] d_in,
    output logic [N-1:0] q_out);
    logic [N-1:0] src = '0;
    always_ff @(posedge clk_a) src <= d_in ^ {src[N-2:0], src[N-1]};      // launch flops: one per bit, some logic in front
    logic [N-1:0] s1, s2;
    if (AREG != 0) begin : g_attr
        (* ASYNC_REG = "TRUE" *) logic [N-1:0] a1 = '0;
        (* ASYNC_REG = "TRUE" *) logic [N-1:0] a2 = '0;
        always_ff @(posedge clk_b) begin a1 <= src; a2 <= a1; end
        assign s1 = a1; assign s2 = a2;
    end else begin : g_plain
        logic [N-1:0] p1 = '0;
        logic [N-1:0] p2 = '0;
        always_ff @(posedge clk_b) begin p1 <= src; p2 <= p1; end
        assign s1 = p1; assign s2 = p2;
    end
    // destination logic: every synchronised bit fans out to several flops (a realistic pull on the second stage)
    logic [N-1:0] acc = '0, acc2 = '0, acc3 = '0;
    always_ff @(posedge clk_b) begin
        acc  <= acc ^ s2 ^ {s2[0], s2[N-1:1]};
        acc2 <= acc2 + {{(N-8){1'b0}}, s2[7:0]} + {s2[N-1:N-8], {(N-8){1'b0}}};
        acc3 <= (acc & s2) | (acc2 ^ {s2[1:0], s2[N-1:2]});
    end
    always_ff @(posedge clk_b) q_out <= acc ^ acc2 ^ acc3;
endmodule
