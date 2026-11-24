// fft_bfp_out_pair: the block-floating-point output stage of fft_mdc2_axis_par2 (arith brief 168): the pair-wise sibling of fft_bfp_out (brief 161).
//
// Takes the pairs of an unscaled 2-parallel transform (WC = W + LOGN bit parts; a frame is H = N/2 consecutive pairs, the first with in_sof, in the BIT-REVERSED pair order of the core, ORDER = 1) into one of NB banks and
// collects, while it writes, the OR of the ones-complement magnitudes of all four parts of every pair (x for x >= 0, -x - 1 for x < 0). When a frame is complete its bank is read out in H consecutive beats, in natural pair
// order (the read address is the bit reversal of the output position in LOGN - 1 bits): pair k is (X[k], X[k + N/2]). The bit length BL of the OR gives the frame exponent s = BL + 1 - W: every part is shifted right by s
// (rounded half up when RND = 1, floored when RND = 0; a negative s shifts LEFT, exactly) and a positive part the rounding carries to 2**(W-1) is saturated to 2**(W-1) - 1. out_exp = s (signed, EW bits),
// the same on every beat of a frame; the true value of a part is out_part * 2**s. out_last marks the H-th beat of a frame (a frame's first beat is the one after a last beat or after reset).
//
// Writing cannot be stalled (the core streams); the caller guarantees that no more than NB frames are in flight (fft_mdc2_axis_ctl's credit), so a bank is free when a frame starts to arrive.
// out_ready stalls the read-out: out_valid, out_last, the data and out_exp are held while out_valid is high and out_ready low. out_valid comes from a register, never from out_ready.
// Timing: the first beat of a frame leaves H + 2 clocks after the core's first output pair.
//
// Intended primitive use (not yet measured): one memory of NB banks x H words x 4 * WC bits (block RAM; for N = 1024, W = 16, NB = 3: 3 x 512 x 104 bits = 156 Kbit), a W + LOGN + W bit
// barrel shifter per part and a priority encoder for the exponent (about 6 * (W + LOGN) LUTs shared, 4 shifters), and a few dozen flip-flops of control.
module fft_bfp_out_pair #(
    parameter int LOGN = 6,
    parameter int W    = 16,
    parameter int RND  = 1,
    parameter int NB   = 3
) (
    input  logic                        clk,
    input  logic                        rst,
    input  logic                        in_valid,
    input  logic                        in_sof,
    input  logic [W+LOGN-1:0]           in_re0,
    input  logic [W+LOGN-1:0]           in_im0,
    input  logic [W+LOGN-1:0]           in_re1,
    input  logic [W+LOGN-1:0]           in_im1,
    input  logic                        out_ready,
    output logic                        out_valid,
    output logic                        out_last,
    output logic [W-1:0]                out_re0,
    output logic [W-1:0]                out_im0,
    output logic [W-1:0]                out_re1,
    output logic [W-1:0]                out_im1,
    output logic [$clog2(2*W+LOGN):0]   out_exp
);
    localparam int H  = 1 << (LOGN - 1);
    localparam int PW = LOGN - 1;
    localparam int WC = W + LOGN;
    localparam int EW = $clog2(2 * W + LOGN) + 1;
    localparam int WN = WC + W + 1;
    localparam int BW = $clog2(NB);

    // ---- write side ---------------------------------------------------------------------------------------------------------------------
    logic [BW-1:0]  wb;
    logic [PW-1:0]  wcnt, wpos;
    logic [WC-1:0]  acc, acc_n;
    logic [WC-1:0]  accs [NB];
    logic [NB-1:0]  full;
    logic           wlast;
    always_comb begin
        wpos  = in_sof ? '0 : wcnt;
        wlast = (wpos == PW'(H - 1));
        acc_n = (in_sof ? '0 : acc) | (in_re0 ^ {WC{in_re0[WC-1]}}) | (in_im0 ^ {WC{in_im0[WC-1]}}) | (in_re1 ^ {WC{in_re1[WC-1]}}) | (in_im1 ^ {WC{in_im1[WC-1]}});
    end

    logic [4*WC-1:0] mem [NB * H];
    logic [4*WC-1:0] rd;
    logic            busy, rlast, issue, en, ov;
    logic [BW-1:0]   rb;
    logic [PW-1:0]   rcnt, idx, ridx, rbr;
    logic [WC-1:0]   acc_sel;
    always_comb begin
        en      = !(ov && !out_ready);
        issue   = busy || full[rb];
        idx     = busy ? rcnt : '0;
        rlast   = (idx == PW'(H - 1));
        for (int i = 0; i < PW; i++) rbr[i] = idx[PW-1-i];
        ridx    = rbr;
        acc_sel = accs[rb];
    end
    always_ff @(posedge clk) begin
        if (in_valid) begin
            mem[int'(wb) * H + int'(wpos)] <= {in_re0, in_im0, in_re1, in_im1};
            acc <= acc_n;
        end
        if (en) rd <= mem[int'(rb) * H + int'(ridx)];
    end
    always_ff @(posedge clk) begin
        if (in_valid && wlast) accs[wb] <= acc_n;
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            wb   <= '0;
            wcnt <= '0;
            full <= '0;
            busy <= 1'b0;
            rb   <= '0;
            rcnt <= '0;
        end else begin
            if (en && issue) begin
                rcnt <= idx + 1'b1;
                busy <= !rlast;
                if (rlast) begin
                    rb       <= (rb == BW'(NB - 1)) ? '0 : rb + 1'b1;
                    full[rb] <= 1'b0;
                end
            end
            if (in_valid) begin
                wcnt <= wpos + 1'b1;
                if (wlast) begin
                    wb       <= (wb == BW'(NB - 1)) ? '0 : wb + 1'b1;
                    full[wb] <= 1'b1;
                end
            end
        end
    end

    // ---- the exponent: s = BL + 1 - W, BL the bit length of the OR of the magnitudes ---------------------------------------------------------
    logic [EW-1:0] sh_new;
    always_comb begin
        int bl;
        bl = 0;
        for (int i = 0; i < WC; i++) if (acc_sel[i]) bl = i + 1;
        sh_new = EW'(bl + 1 - W);
    end

    // ---- read pipeline: issue (address), memory read, shift and register ------------------------------------------------------------------------
    logic          v1, l1, ol;
    logic [EW-1:0] e1;
    always_ff @(posedge clk) begin
        if (rst) begin
            v1       <= 1'b0;
            l1       <= 1'b0;
            ov       <= 1'b0;
            ol       <= 1'b0;
        end else if (en) begin
            v1       <= issue;
            l1       <= issue && rlast;
            ov       <= v1;
            ol       <= l1;
        end
        if (en) e1 <= sh_new;
    end
    assign out_valid = ov;
    assign out_last  = ol;

    function automatic logic [W-1:0] norm(input logic signed [WC-1:0] x, input logic signed [EW-1:0] s);
        logic signed [WN-1:0] t;
        int shr, shl;
        shr = (s > 0) ? int'(s) : 0;
        shl = (s < 0) ? -int'(s) : 0;
        t   = WN'(x) <<< shl;
        if (RND != 0 && shr > 0) t = t + (WN'(1) <<< (shr - 1));
        t   = t >>> shr;
        if (t > WN'((1 <<< (W - 1)) - 1)) t = WN'((1 <<< (W - 1)) - 1);
        return t[W-1:0];
    endfunction
    always_ff @(posedge clk) begin
        if (en) begin
            out_re0 <= norm(rd[4*WC-1:3*WC], e1);
            out_im0 <= norm(rd[3*WC-1:2*WC], e1);
            out_re1 <= norm(rd[2*WC-1:WC], e1);
            out_im1 <= norm(rd[WC-1:0], e1);
            out_exp <= e1;
        end
    end
endmodule
