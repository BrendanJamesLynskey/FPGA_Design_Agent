// fxp_round_fold: round (truncate / half up / convergent) and saturate in one clock with ONE adder (brief 139b). Latency 1.
// The rounding is folded into the carry: sum = x + C + cin, C = 0 (truncate), 2**(S-1) (half up), 2**(S-1) - 1 (convergent) and, for
// convergent only, cin = x[S] (the bit that becomes the result's LSB: a tie rounds up exactly when that bit is 1). The result is sum >>> S.
// Primitive use (intended, not yet measured): the adder is one carry chain of ceil((W_IN+1)/4) CARRY4 whose constant operand is a
// pattern of 0s and 1s (the low S bits of the sum are discarded, so only the carry out of them matters); the carry-in is the chain's CIN
// pin for convergent. Saturation (fxp_sat) is a LUT level after the chain. No DSP, no block RAM.
module fxp_round_fold #(
    parameter int W_IN  = 16,
    parameter int S     = 4,              // fractional bits dropped, 0 to W_IN - 1
    parameter int W_OUT = 12,             // 2 or more
    parameter int MODE  = 2,              // 0 truncate, 1 round half up, 2 convergent
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

    logic [W_IN:0] xe, cst, sum;
    logic          cin;
    logic [W_R-1:0] r;
    logic [W_OUT-1:0] y_c;

    assign in_ready = 1'b1;
    assign xe  = {x[W_IN-1], x};
    assign cst = (S == 0 || MODE == 0) ? '0 : (MODE == 1) ? ((W_IN + 1)'(1) << SM1) : (((W_IN + 1)'(1) << SM1) - (W_IN + 1)'(1));
    assign cin = (S > 0 && MODE == 2) ? x[S] : 1'b0;
    assign sum = xe + cst + {{W_IN{1'b0}}, cin};
    assign r   = sum[W_IN:S];

    fxp_sat #(.W_R(W_R), .W_OUT(W_OUT), .SAT(SAT)) u_sat (.r, .y(y_c));

    always_ff @(posedge clk) begin
        if (rst) out_valid <= 1'b0;
        else     out_valid <= in_valid;
    end
    always_ff @(posedge clk) y <= y_c;
    if (S > 0) begin : g_low
        logic unused;
        assign unused = &{1'b0, sum[S-1:0]};
    end
endmodule
