// fp_fma_fv: formal equivalence of the floating-point multiply-add variants with the specification as wide integer arithmetic (arith brief 139e).
// fused (STAGES = ST_F) is compared with fpx_ref (OP = 2), the exact a * b + c rounded once; cascade (STAGES_M = ST_M, STAGES_A = ST_A) with TWO rounded steps of the reference, fpx_ref
// (OP = 1) then fpx_ref (OP = 0), which is the specification of the double rounding. Each is compared with the reference delayed by its own latency once that many clocks have passed
// since the start. Inputs are free in every clock. Run by tools/run_formal.py (SymbiYosys, slang front end).
module fp_fma_fv #(
    parameter int EXP     = 2,
    parameter int MAN     = 2,
    parameter int SUBNORM = 1,
    parameter int ST_F    = 4,
    parameter int ST_M    = 2,
    parameter int ST_A    = 1
) (
    input logic                clk,
    input logic [EXP+MAN:0]    a,
    input logic [EXP+MAN:0]    b,
    input logic [EXP+MAN:0]    c
);
    localparam int W = EXP + MAN + 1;
    logic [W-1:0] y_fused_ref, y_prod_ref, y_casc_ref, y_f, y_c;
    fpx_ref #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .OP(2)) u_ref_f (.a(a), .b(b), .c(c), .y(y_fused_ref));
    fpx_ref #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .OP(1)) u_ref_m (.a(a), .b(b), .c('0), .y(y_prod_ref));
    fpx_ref #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .OP(0)) u_ref_a (.a(y_prod_ref), .b(c), .c('0), .y(y_casc_ref));
    fp_fma_fused   #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .STAGES(ST_F))                       u_f (.clk(clk), .a(a), .b(b), .c(c), .y(y_f));
    fp_fma_cascade #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .STAGES_M(ST_M), .STAGES_A(ST_A))    u_c (.clk(clk), .a(a), .b(b), .c(c), .y(y_c));

    localparam int LC = ST_M + ST_A;
    logic [W-1:0] df [4];                        // the fused reference, delayed 1 .. 4 clocks
    logic [W-1:0] dc [6];                        // the cascade reference, delayed 1 .. 6 clocks
    logic [2:0]   warm = 3'd0;                   // clocks since the start, saturating at 7
    always_ff @(posedge clk) begin
        df[0] <= y_fused_ref;
        for (int i = 1; i < 4; i++) df[i] <= df[i-1];
        dc[0] <= y_casc_ref;
        for (int i = 1; i < 6; i++) dc[i] <= dc[i-1];
        if (warm != 3'd7) warm <= warm + 3'd1;
    end
    always_comb begin
        P_FUSED:   assert (ST_F == 0 ? y_f == y_fused_ref : (warm < 3'(ST_F) || y_f == df[ST_F-1]));
        P_CASCADE: assert (LC == 0 ? y_c == y_casc_ref : (warm < 3'(LC) || y_c == dc[LC-1]));
    end
endmodule
