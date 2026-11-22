// fp_mul_fv: formal equivalence of the floating-point multiplier variants with the specification as wide integer arithmetic (arith brief 139e).
// The reference is fpx_ref (OP = 1): the exact product in a fixed-point window, rounded once, sharing no code with the variants. Each variant (STAGES = ST_D, ST_L) is compared with the
// reference delayed by its own latency, once that many clocks have passed since the start. Inputs are free in every clock. Run by tools/run_formal.py (SymbiYosys, slang front end).
module fp_mul_fv #(
    parameter int EXP     = 3,
    parameter int MAN     = 2,
    parameter int SUBNORM = 1,
    parameter int ST_D    = 3,
    parameter int ST_L    = 2
) (
    input logic                clk,
    input logic [EXP+MAN:0]    a,
    input logic [EXP+MAN:0]    b
);
    localparam int W = EXP + MAN + 1;
    logic [W-1:0] y_ref, y_d, y_l;
    fpx_ref   #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .OP(1))            u_ref (.a(a), .b(b), .c('0), .y(y_ref));
    fp_mul_dsp #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .STAGES(ST_D))    u_d   (.clk(clk), .a(a), .b(b), .y(y_d));
    fp_mul_lut #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .STAGES(ST_L))    u_l   (.clk(clk), .a(a), .b(b), .y(y_l));

    logic [W-1:0] d [3];                         // the reference result, delayed 1 .. 3 clocks
    logic [1:0]   warm = 2'd0;                   // clocks since the start, saturating at 3
    always_ff @(posedge clk) begin
        d[0] <= y_ref;
        d[1] <= d[0];
        d[2] <= d[1];
        if (warm != 2'd3) warm <= warm + 2'd1;
    end
    always_comb begin
        P_DSP: assert (ST_D == 0 ? y_d == y_ref : (warm < 2'(ST_D) || y_d == d[ST_D-1]));
        P_LUT: assert (ST_L == 0 ? y_l == y_ref : (warm < 2'(ST_L) || y_l == d[ST_L-1]));
    end
endmodule
