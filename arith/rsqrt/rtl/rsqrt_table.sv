// rsqrt_table: reciprocal square root from the seed table alone (brief 139c): one register stage, no multiplier.
//   y = seed(x) with F = W fractional bits; the error is at most 2**(W-A-2) + 1 units of the last place (model.error_range).
module rsqrt_table #(
    parameter int W = 16,
    parameter int A = 7
) (
    input  logic          clk,
    input  logic          rst,
    input  logic          in_valid,
    output logic          in_ready,
    input  logic [W-1:0]  x,
    output logic          out_valid,
    output logic [W:0]    y
);
    logic [W-1:0] y0;
    rsqrt_seed #(.W(W), .A(A), .F(W)) u_seed (.x, .y(y0));
    assign in_ready = 1'b1;
    always_ff @(posedge clk) y <= {1'b0, y0};
    always_ff @(posedge clk) begin
        if (rst) out_valid <= 1'b0;
        else     out_valid <= in_valid;
    end
endmodule
