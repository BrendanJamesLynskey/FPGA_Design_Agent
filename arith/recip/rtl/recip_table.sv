// recip_table: reciprocal from the seed table alone (brief 139c): one register stage, no multiplier.
//   y = seed(b) with F = W fractional bits; the error is at most 2**(W-A-1) + 1/2 units of the last place (model.error_range).
// Primitive use (intended, not yet measured): the seed ROM (LUTs or a block RAM) and W + 1 flip-flops; no DSP.
module recip_table #(
    parameter int W = 16,
    parameter int A = 7
) (
    input  logic          clk,
    input  logic          rst,
    input  logic          in_valid,
    output logic          in_ready,
    input  logic [W-1:0]  b,
    output logic          out_valid,
    output logic [W:0]    y
);
    logic [W-1:0] y0;
    recip_seed #(.W(W), .A(A), .F(W)) u_seed (.b, .y(y0));
    assign in_ready = 1'b1;
    always_ff @(posedge clk) y <= {1'b0, y0};
    always_ff @(posedge clk) begin
        if (rst) out_valid <= 1'b0;
        else     out_valid <= in_valid;
    end
endmodule
