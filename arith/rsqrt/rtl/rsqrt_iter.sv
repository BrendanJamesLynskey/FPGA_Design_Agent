// rsqrt_iter: one Newton-Raphson step for the reciprocal square root, five register stages (brief 139c).
//   Inputs x (W bits, 2 integer bits, x / 2**(W-2) in [1, 4)) and y (YW = F + 1 bits, the current estimate of 2**F / sqrt(X), at most 2**F);
//   outputs y_o the improved estimate and x_o the operand delayed to match. Stage 1: s = (y * y) >> F (a multiplier YW x YW). Stage 2: t = x * s (W x YW).
//   Stage 3: d = (2**(W-2+F) - t) >> (W-2), the residual 1 - X*y*y in units of 2**-F, floor, signed, DW = F - A + 2 bits (model.dw). Stage 4: p = y * d.
//   Stage 5: y_o = y + (p >> (F + 1)).
// Primitive use (intended, not yet measured): three DSP multipliers (one DSP48E1 each when the operands fit 25 x 18, more above), the residual
// subtract in fabric; fully pipelined, one estimate per clock.
module rsqrt_iter #(
    parameter int W  = 16,
    parameter int A  = 7,
    parameter int F  = 18
) (
    input  logic          clk,
    input  logic [W-1:0]  x,
    input  logic [F:0]    y,
    output logic [W-1:0]  x_o,
    output logic [F:0]    y_o
);
    localparam int YW = F + 1;
    localparam int DW = F - A + 2;
    localparam int TW = W + YW;           // x * s
    localparam int RW = TW + 1;           // 2**(W-2+F) - t, signed

    logic [W-1:0]    x1, x2, x3, x4;
    logic [YW-1:0]   y1, y2, y3, y4;
    logic [2*YW-1:0] sq_w;
    logic [YW-1:0]   s_q;
    logic [TW-1:0]   t_q;
    logic signed [DW-1:0] d_q;
    logic signed [YW+DW:0] p_q;
    logic signed [RW-1:0] r_w, d_full;
    logic            unused;

    always_comb begin
        sq_w   = y * y;
        r_w    = $signed(RW'(1) << (W - 2 + F)) - $signed({1'b0, t_q});
        d_full = r_w >>> (W - 2);
    end
    assign unused = &{1'b0, sq_w[F-1:0], sq_w[2*YW-1:F+YW], d_full[RW-1:DW]};   // s <= 2**F and the residual fits DW bits (asserted by the model and the proofs)

    always_ff @(posedge clk) begin
        s_q <= sq_w[F +: YW];                          // stage 1
        x1  <= x;
        y1  <= y;
        t_q <= x1 * s_q;                               // stage 2
        x2  <= x1;
        y2  <= y1;
        d_q <= d_full[DW-1:0];                         // stage 3
        x3  <= x2;
        y3  <= y2;
        p_q <= $signed({1'b0, y3}) * d_q;              // stage 4
        x4  <= x3;
        y4  <= y3;
        y_o <= YW'(y4 + YW'(p_q >>> (F + 1)));         // stage 5
        x_o <= x4;
    end
endmodule
