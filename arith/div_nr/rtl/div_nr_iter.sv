// div_nr_iter: one Newton-Raphson step of the Newton divider (the reciprocal of b), four register stages (brief 139c).
//   Inputs b (W bits, normalised) and y (YW = F + 1 bits, the current estimate of 2**F / B, at most 2**F); output y_o the improved estimate and
//   b_o the divisor delayed to match. Stage 1: t = b * y (one multiplier W x YW). Stage 2: d = (2**(W-1+F) - t) >> (W-1), the residual 1 - B*y in
//   units of 2**-F, floor, signed, DW = F - A + 1 bits (the first step's residual is below 2**(F-A) in magnitude: model.dw). Stage 3: p = y * d
//   (a second multiplier YW x DW). Stage 4: y_o = y + (p >> F) (arithmetic shift).
// Primitive use (intended, not yet measured): two DSP multipliers, each one DSP48E1 (25 x 18) when W <= 25 and YW <= 18 and DW <= 25 (one more
// for each step up in operand size), the residual subtract in fabric; fully pipelined, one estimate per clock.
module div_nr_iter #(
    parameter int W  = 16,
    parameter int A  = 7,
    parameter int F  = 18                 // fractional bits of y: W + 2 guard bits
) (
    input  logic          clk,
    input  logic [W-1:0]  b,
    input  logic [F:0]    y,
    output logic [W-1:0]  b_o,
    output logic [F:0]    y_o
);
    localparam int YW = F + 1;
    localparam int DW = F - A + 1;
    localparam int TW = W + YW;           // b * y
    localparam int RW = TW + 1;           // 2**(W-1+F) - t, signed

    logic [W-1:0]    b1, b2, b3;
    logic [YW-1:0]   y1, y2, y3;
    logic [TW-1:0]   t_q;
    logic signed [DW-1:0] d_q;
    logic signed [YW+DW:0] p_q;           // signed product of y (as non-negative) and d
    logic signed [RW-1:0] r_w;
    logic signed [RW-1:0] d_full;
    logic            unused;

    always_comb begin
        r_w    = $signed(RW'(1) << (W - 1 + F)) - $signed({1'b0, t_q});
        d_full = r_w >>> (W - 1);
    end
    assign unused = &{1'b0, d_full[RW-1:DW]};         // the residual fits its DW-bit word (asserted by the model and the proofs)

    always_ff @(posedge clk) begin
        t_q <= b * y;                                  // stage 1
        b1  <= b;
        y1  <= y;
        d_q <= d_full[DW-1:0];                         // stage 2
        b2  <= b1;
        y2  <= y1;
        p_q <= $signed({1'b0, y2}) * d_q;              // stage 3
        b3  <= b2;
        y3  <= y2;
        y_o <= YW'(y3 + YW'(p_q >>> F));               // stage 4
        b_o <= b3;
    end
endmodule
