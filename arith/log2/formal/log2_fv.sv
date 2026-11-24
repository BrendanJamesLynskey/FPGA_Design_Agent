// log2_fv: formal error bounds of the log2 variants (arith brief 139d). The reference is log2_ref, the exact function on 8 input bits to 24 fractional bits straight from
// the maths library. SEL picks which variants this run instantiates and checks (1 table, 2 lerp, 4 poly2, 8 cordic; add them to check several), so each job is a small
// problem. Each variant (lerp with SBL segment bits, poly2 with SBP, cordic with NIT iterations and G guard bits; all at IW = 8 and OW bits out) is compared with the
// reference delayed by its own latency once that many clocks have passed since the start: |y * 2**(24 - OW) - reference| <= B (BT, BL, BP, BC, in units of 2**-24; the jobs
// choose them from the measured error of the model plus one unit for the reference's own rounding). The table variant's registered form is also compared with its
// combinational form. Inputs are free in every clock; a proof is by k-induction (for all inputs, any run length). Run by tools/run_formal.py (SymbiYosys, slang front end).
module log2_fv #(
    parameter int SEL = 15,
    parameter int OW  = 10,
    parameter int SBL = 4,
    parameter int SBP = 3,
    parameter int NIT = 12,
    parameter int G   = 4,
    parameter int BT  = 0,
    parameter int BL  = 0,
    parameter int BP  = 0,
    parameter int BC  = 0
) (
    input logic       clk,
    input logic [7:0] x
);
    logic [23:0]   r;
    log2_ref u_ref (.x(x), .r(r));
    logic [23:0] d [26];                         // the reference delayed 1 .. 26 clocks
    logic [4:0]  warm = 5'd0;                    // clocks since the start, saturating at 31
    always_ff @(posedge clk) begin
        d[0] <= r;
        for (int j = 1; j < 26; j++) d[j] <= d[j-1];
        if (warm != 5'd31) warm <= warm + 5'd1;
    end
    function automatic logic close_to(input logic [OW-1:0] y, input logic [23:0] ref_v, input int b);
        logic [24:0] ys, df;
        ys = 25'(y) << (24 - OW);
        df = (ys >= {1'b0, ref_v}) ? ys - {1'b0, ref_v} : {1'b0, ref_v} - ys;
        close_to = (df <= 25'(b));
    endfunction
    if ((SEL & 1) != 0) begin : g_t
        logic [OW-1:0] t0, t1, t0_d;
        log2_table #(.IW(8), .OW(OW), .REG(0)) u_t0 (.clk(clk), .x(x), .y(t0));
        log2_table #(.IW(8), .OW(OW), .REG(1)) u_t1 (.clk(clk), .x(x), .y(t1));
        always_ff @(posedge clk) t0_d <= t0;
        always_comb begin
            P_TABLE:     assert (close_to(t0, r, BT));
            P_TABLE_REG: assert (warm < 5'd1 || t1 == t0_d);
        end
    end
    if ((SEL & 2) != 0) begin : g_l
        logic [OW-1:0] y;
        log2_lerp #(.IW(8), .OW(OW), .SB(SBL)) u (.clk(clk), .x(x), .y(y));
        always_comb P_LERP: assert (warm < 5'd2 || close_to(y, d[1], BL));
    end
    if ((SEL & 4) != 0) begin : g_p
        logic [OW-1:0] y;
        log2_poly2 #(.IW(8), .OW(OW), .SB(SBP)) u (.clk(clk), .x(x), .y(y));
        always_comb P_POLY2: assert (warm < 5'd3 || close_to(y, d[2], BP));
    end
    if ((SEL & 8) != 0) begin : g_c
        logic [OW-1:0] y;
        log2_cordic #(.IW(8), .OW(OW), .NIT(NIT), .G(G)) u (.clk(clk), .x(x), .y(y));
        always_comb P_CORDIC: assert (warm < 5'(NIT + 1) || close_to(y, d[NIT], BC));
    end
endmodule
