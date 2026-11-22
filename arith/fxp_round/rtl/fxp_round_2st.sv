// fxp_round_2st: the fold-adder rounding of fxp_round_fold with a register between the adder and the saturation (brief 139b). Latency 2.
// Primitive use (intended, not yet measured): as fxp_round_fold plus W_R flip-flops after the carry chain; the saturation LUT level sits
// alone in the second stage, so the clock is set by the carry chain (or the output routing), not chain plus saturation.
module fxp_round_2st #(
    parameter int W_IN  = 16,
    parameter int S     = 4,
    parameter int W_OUT = 12,
    parameter int MODE  = 2,
    parameter bit SAT   = 1'b1
) (
    input  logic             clk,
    input  logic             rst,
    input  logic             in_valid,
    output logic             in_ready,
    input  logic [W_IN-1:0]  x,
    output logic             out_valid,
    output logic [W_OUT-1:0] y
);
    localparam int W_R = W_IN - S + 1;
    localparam int SM1 = (S > 0) ? S - 1 : 0;

    logic [W_IN:0]    xe, cst, sum;
    logic             cin, v1;
    logic [W_R-1:0]   r, r_q;
    logic [W_OUT-1:0] y_c;

    assign in_ready = 1'b1;
    assign xe  = {x[W_IN-1], x};
    assign cst = (S == 0 || MODE == 0) ? '0 : (MODE == 1) ? ((W_IN + 1)'(1) << SM1) : (((W_IN + 1)'(1) << SM1) - (W_IN + 1)'(1));
    assign cin = (S > 0 && MODE == 2) ? x[S] : 1'b0;
    assign sum = xe + cst + {{W_IN{1'b0}}, cin};
    assign r   = sum[W_IN:S];

    always_ff @(posedge clk) r_q <= r;
    fxp_sat #(.W_R(W_R), .W_OUT(W_OUT), .SAT(SAT)) u_sat (.r(r_q), .y(y_c));
    always_ff @(posedge clk) y <= y_c;

    always_ff @(posedge clk) begin
        if (rst) begin
            v1        <= 1'b0;
            out_valid <= 1'b0;
        end else begin
            v1        <= in_valid;
            out_valid <= v1;
        end
    end
    if (S > 0) begin : g_low
        logic unused;
        assign unused = &{1'b0, sum[S-1:0]};
    end
endmodule
