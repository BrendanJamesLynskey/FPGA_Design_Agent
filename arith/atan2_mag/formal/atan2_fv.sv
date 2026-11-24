// atan2_fv: formal checks of the atan2_mag variants (arith brief 139d). The reference is atan2_ref, the exact angle (turns, 24 fractional bits) and length (16 fractional bits) of a
// vector of two 4-bit coordinates straight from the maths library. SEL picks the checks of this run (1 cordic, 2 cordic_g2, 4 the two variants bit for bit; add them to check
// several), so each job is a small problem. Both variants (W = 4, PH, NIT iterations, G guard bits; GRP iterations per register in the second) are compared with the reference
// delayed by their own latency once that many clocks have passed since the start: the angle within BA units of 2**-24 turn (round the circle) and the length within BM units of
// 2**-16 (the origin's angle is not compared). The second variant's outputs are also compared bit for bit with the first's (they are the same function), the faster one delayed to
// meet the slower. Inputs are free in every clock; a proof is by k-induction (for all inputs, any run length). Run by tools/run_formal.py (SymbiYosys, slang front end).
module atan2_fv #(
    parameter int SEL = 7,
    parameter int PH  = 8,
    parameter int NIT = 8,
    parameter int G   = 6,
    parameter int GRP = 2,
    parameter int BA  = 0,
    parameter int BM  = 0
) (
    input logic       clk,
    input logic [3:0] x,
    input logic [3:0] y
);
    localparam int LC = NIT + 2;                                // latency of cordic
    localparam int LG = (NIT + GRP - 1) / GRP + 2;              // latency of cordic_g2
    logic [23:0] ra;
    logic [20:0] rm;
    atan2_ref u_ref (.x(x), .y(y), .ang(ra), .mag(rm));
    logic [23:0] da [28];                        // the reference angle, length and origin flag delayed 1 .. 28 clocks
    logic [20:0] dm [28];
    logic        dz [28];
    logic [4:0]  warm = 5'd0;                    // clocks since the start, saturating at 31
    always_ff @(posedge clk) begin
        da[0] <= ra;
        dm[0] <= rm;
        dz[0] <= (x == 4'd0 && y == 4'd0);
        for (int j = 1; j < 28; j++) begin
            da[j] <= da[j-1];
            dm[j] <= dm[j-1];
            dz[j] <= dz[j-1];
        end
        if (warm != 5'd31) warm <= warm + 5'd1;
    end
    function automatic logic ang_ok(input logic [PH-1:0] a, input logic [23:0] ref_v, input logic origin);
        logic [24:0] as, df;
        as = 25'(a) << (24 - PH);
        df = (as >= {1'b0, ref_v}) ? as - {1'b0, ref_v} : {1'b0, ref_v} - as;
        if (df > 25'h0800000) df = 25'h1000000 - df;             // circular: the shorter way round
        ang_ok = origin || (df <= 25'(BA));
    endfunction
    function automatic logic mag_ok(input logic [3:0] m, input logic [20:0] ref_v);
        logic [20:0] ms, df;
        ms = 21'(m) << 16;
        df = (ms >= ref_v) ? ms - ref_v : ref_v - ms;
        mag_ok = (df <= 21'(BM));
    endfunction
    if ((SEL & 1) != 0) begin : g_c
        logic [PH-1:0] a;
        logic [3:0]    m;
        atan2_cordic #(.W(4), .PH(PH), .NIT(NIT), .G(G)) u (.clk(clk), .x(x), .y(y), .ang(a), .mag(m));
        always_comb begin
            P_CORDIC_ANG: assert (warm < 5'(LC) || ang_ok(a, da[LC-1], dz[LC-1]));
            P_CORDIC_MAG: assert (warm < 5'(LC) || mag_ok(m, dm[LC-1]));
        end
    end
    if ((SEL & 2) != 0) begin : g_g
        logic [PH-1:0] a;
        logic [3:0]    m;
        atan2_cordic_g2 #(.W(4), .PH(PH), .NIT(NIT), .G(G), .GRP(GRP)) u (.clk(clk), .x(x), .y(y), .ang(a), .mag(m));
        always_comb begin
            P_G2_ANG: assert (warm < 5'(LG) || ang_ok(a, da[LG-1], dz[LG-1]));
            P_G2_MAG: assert (warm < 5'(LG) || mag_ok(m, dm[LG-1]));
        end
    end
    if ((SEL & 4) != 0) begin : g_s
        logic [PH-1:0]   ac, ag;
        logic [3:0]      mc, mg;
        logic [PH+3:0]   dg [28];                // cordic_g2's outputs delayed
        atan2_cordic    #(.W(4), .PH(PH), .NIT(NIT), .G(G))              u_c (.clk(clk), .x(x), .y(y), .ang(ac), .mag(mc));
        atan2_cordic_g2 #(.W(4), .PH(PH), .NIT(NIT), .G(G), .GRP(GRP))   u_g (.clk(clk), .x(x), .y(y), .ang(ag), .mag(mg));
        always_ff @(posedge clk) begin
            dg[0] <= {ag, mg};
            for (int j = 1; j < 28; j++) dg[j] <= dg[j-1];
        end
        always_comb P_SAME: assert (warm < 5'(LC) || {ac, mc} == (LC == LG ? {ag, mg} : dg[LC-LG-1]));
    end
endmodule
