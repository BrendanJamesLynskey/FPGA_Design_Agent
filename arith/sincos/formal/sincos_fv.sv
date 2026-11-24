// sincos_fv: formal error bounds of the sincos variants (arith brief 139d). The reference is sincos_ref, the exact sine and cosine of an 8-bit phase to 24 fractional bits straight
// from the maths library. SEL picks which variants this run instantiates and checks (1 lerp, 2 poly2, 4 cordic; add them to check several), so each job is a small problem. Each
// variant (lerp with SBL segment bits, poly2 with SBP, cordic with NIT iterations and G guard bits; all at PH = 8 and OW bits out) is compared with the reference delayed by its
// own latency once that many clocks have passed since the start: |s * 2**(25 - OW) - reference| <= B and the same for the cosine (BL, BP, BC, in units of 2**-24; the jobs choose them
// from the measured error of the model plus one unit for the reference's own rounding). This covers the quadrant map as well as the arithmetic. Inputs are free in every clock; a proof
// is by k-induction (for all inputs, any run length). Run by tools/run_formal.py (SymbiYosys, slang front end).
module sincos_fv #(
    parameter int SEL = 7,
    parameter int OW  = 8,
    parameter int SBL = 3,
    parameter int SBP = 3,
    parameter int NIT = 8,
    parameter int G   = 3,
    parameter int BL  = 0,
    parameter int BP  = 0,
    parameter int BC  = 0
) (
    input logic       clk,
    input logic [7:0] phase
);
    logic signed [25:0] rs, rc;
    sincos_ref u_ref (.phase(phase), .s(rs), .c(rc));
    logic signed [25:0] ds [26];                 // the reference delayed 1 .. 26 clocks
    logic signed [25:0] dc [26];
    logic [4:0]  warm = 5'd0;                    // clocks since the start, saturating at 31
    always_ff @(posedge clk) begin
        ds[0] <= rs;
        dc[0] <= rc;
        for (int j = 1; j < 26; j++) begin
            ds[j] <= ds[j-1];
            dc[j] <= dc[j-1];
        end
        if (warm != 5'd31) warm <= warm + 5'd1;
    end
    function automatic logic close_to(input logic signed [OW-1:0] y, input logic signed [25:0] ref_v, input int b);
        logic signed [27:0] ys, df;
        ys = 28'(y) <<< (25 - OW);               // the output has OW - 1 fractional bits; 24 for the reference
        df = ys - 28'(ref_v);
        if (df < 0) df = -df;
        close_to = (df <= 28'(b));
    endfunction
    if ((SEL & 1) != 0) begin : g_l
        logic signed [OW-1:0] s, c;
        sincos_lerp #(.PH(8), .OW(OW), .SB(SBL)) u (.clk(clk), .phase(phase), .s(s), .c(c));
        always_comb P_LERP: assert (warm < 5'd2 || (close_to(s, ds[1], BL) && close_to(c, dc[1], BL)));
    end
    if ((SEL & 2) != 0) begin : g_p
        logic signed [OW-1:0] s, c;
        sincos_poly2 #(.PH(8), .OW(OW), .SB(SBP)) u (.clk(clk), .phase(phase), .s(s), .c(c));
        always_comb P_POLY2: assert (warm < 5'd3 || (close_to(s, ds[2], BP) && close_to(c, dc[2], BP)));
    end
    if ((SEL & 4) != 0) begin : g_c
        logic signed [OW-1:0] s, c;
        sincos_cordic #(.PH(8), .OW(OW), .NIT(NIT), .G(G)) u (.clk(clk), .phase(phase), .s(s), .c(c));
        always_comb P_CORDIC: assert (warm < 5'(NIT) || (close_to(s, ds[NIT-1], BC) && close_to(c, dc[NIT-1], BC)));
    end
endmodule
