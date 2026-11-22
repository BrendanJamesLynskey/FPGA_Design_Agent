// fft_sdf_stage_fv: the delay-feedback stage computes the radix-2 butterfly of the word that arrived D clocks ago with the word arriving now (arith brief 148).
// The shadow keeps the last 2 * D input words and works on `int` values, sharing no code with the stage. At a clock with tag c (the stage's own counter, restarted by sof):
//  - second half (c[LD] = 1): the registered output, one clock later, is a + b' (halved and rounded when SCALE = 1), with a = the input D clocks ago and b' = the input now, times -j when
//    TYP = 1 and c[LD+1] = 1;
//  - first half (c[LD] = 0): the registered output is the difference of the previous block: a2 - b2' with a2 = the input 2 * D clocks ago, b2' = the input D clocks ago times -j as the tag then said,
//    (halved and rounded when SCALE = 1);
//  - always: pos is c - D.
// Checked when at least 2 * D clocks have passed since the start and since the last sof, over every input sequence (bounded model check from an arbitrary state, because the delay line
// of the stage is not constrained). Run by tools/run_formal.py (SymbiYosys, slang front end).
module fft_sdf_stage_fv #(
    parameter int LOGN  = 4,
    parameter int LD    = 1,
    parameter int TYP   = 0,
    parameter int WI    = 4,
    parameter int SCALE = 1,
    parameter int RND   = 1
) (
    input logic          clk,
    input logic          sof,
    input logic [WI-1:0] xr,
    input logic [WI-1:0] xi
);
    localparam int D  = 1 << LD;
    localparam int WO = (SCALE != 0) ? WI : WI + 1;
    logic [WO-1:0]   yr, yi;
    logic [LOGN-1:0] pos;
    fft_sdf_stage #(.LOGN(LOGN), .LD(LD), .TYP(TYP), .WI(WI), .SCALE(SCALE), .RND(RND)) u (.clk(clk), .sof(sof), .xr(xr), .xi(xi), .yr(yr), .yi(yi), .pos(pos));

    int hr [2*D];
    int hi [2*D];
    int xs_r, xs_i;
    logic [LOGN-1:0] c, cprev;
    logic [5:0] age = 6'd0;
    int er, ei, ar, ai, br, bi, sr, si;
    logic [WO-1:0] er_q, ei_q;
    logic          first_clk = 1'b1;
    logic ev = 1'b0;
    logic [LOGN-1:0] ep;
    logic [LOGN-1:0] pr;
    logic mj, mj2, second;
    logic signed [WI-1:0] sxr, sxi;
    always_comb begin
        sxr = xr; sxi = xi;
        xs_r = int'(sxr);
        xs_i = int'(sxi);
        c      = sof ? '0 : u.cnt;
        cprev  = c - LOGN'(D);
        second = c[LD];
        mj     = (TYP == 1) && c[LD] && c[LD+1];
        mj2    = (TYP == 1) && cprev[LD] && cprev[LD+1];
        pr     = c - LOGN'(D);
        er = 0; ei = 0;
        if (second) begin
            ar = hr[D-1]; ai = hi[D-1];
            br = mj ? xs_i : xs_r;
            bi = mj ? -xs_r : xs_i;
            sr = ar + br; si = ai + bi;
        end else begin
            ar = hr[2*D-1]; ai = hi[2*D-1];
            br = mj2 ? hi[D-1] : hr[D-1];
            bi = mj2 ? -hr[D-1] : hi[D-1];
            sr = ar - br; si = ai - bi;
        end
        er = (SCALE != 0) ? ((sr + RND) >>> 1) : sr;
        ei = (SCALE != 0) ? ((si + RND) >>> 1) : si;
    end
    always_ff @(posedge clk) begin
        hr[0] <= xs_r; hi[0] <= xs_i;
        for (int k = 1; k < 2*D; k++) begin
            hr[k] <= hr[k-1];
            hi[k] <= hi[k-1];
        end
        if (sof) age <= 6'd1;
        else if (age != 6'd63) age <= age + 6'd1;
        ev <= !sof && (age >= 6'(2*D));
        first_clk <= 1'b0;
        ep <= pr;
        er_q <= er[WO-1:0];
        ei_q <= ei[WO-1:0];
    end
    always_comb begin
        BFLY_RE: assert (!ev || first_clk || yr == er_q);
        BFLY_IM: assert (!ev || first_clk || yi == ei_q);
        POS:     assert (first_clk || pos == ep);
    end
endmodule
