// fp_add_fv: formal equivalence of the floating-point adder variants with the specification as wide integer arithmetic (arith brief 139e).
// The reference is fpx_ref (OP = 0): the exact sum in a fixed-point window, rounded once, sharing no code with the variants. Each variant (STAGES = ST_S, ST_D) is compared with the
// reference delayed by its own latency, once that many clocks have passed since the start. Inputs are free in every clock. Run by tools/run_formal.py (SymbiYosys, slang front end).
module fp_add_fv #(
    parameter int EXP     = 3,
    parameter int MAN     = 2,
    parameter int SUBNORM = 1,
    parameter int ST_S    = 3,
    parameter int ST_D    = 2
) (
    input logic                clk,
    input logic [EXP+MAN:0]    a,
    input logic [EXP+MAN:0]    b
);
    localparam int W = EXP + MAN + 1;
    logic [W-1:0] y_ref, y_s, y_d;
    fpx_ref        #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .OP(0))            u_ref (.a(a), .b(b), .c('0), .y(y_ref));
    fp_add_single  #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .STAGES(ST_S))     u_s   (.clk(clk), .a(a), .b(b), .y(y_s));
    fp_add_dual    #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .STAGES(ST_D))     u_d   (.clk(clk), .a(a), .b(b), .y(y_d));

    logic [W-1:0] d [3];                         // the reference result, delayed 1 .. 3 clocks
    logic [1:0]   warm = 2'd0;                   // clocks since the start, saturating at 3
    always_ff @(posedge clk) begin
        d[0] <= y_ref;
        d[1] <= d[0];
        d[2] <= d[1];
        if (warm != 2'd3) warm <= warm + 2'd1;
    end
    always_comb begin
        P_SINGLE: assert (ST_S == 0 ? y_s == y_ref : (warm < 2'(ST_S) || y_s == d[ST_S-1]));
        P_DUAL:   assert (ST_D == 0 ? y_d == y_ref : (warm < 2'(ST_D) || y_d == d[ST_D-1]));
    end
endmodule
