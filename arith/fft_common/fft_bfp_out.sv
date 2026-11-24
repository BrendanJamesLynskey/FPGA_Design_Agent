// fft_bfp_out: the block-floating-point output stage of fft_bfp_sdf and fft_bfp_burst (arith brief 161).
//
// Takes the words of an unscaled transform (WC = W + LOGN bit parts, a frame of N = 2**LOGN consecutive accepted words, the first with in_sof, in the BIT-REVERSED order of the core)
// into one of two banks and collects, while it writes, the OR of the ones-complement magnitudes of every part (x for x >= 0, -x - 1 for x < 0). When the frame is complete the
// bank is read out in N consecutive clocks, in natural order (ORDER = 0: the read address is the bit reversal of the output position) or in the core's bit-reversed order
// (ORDER = 1). The bit length BL of the OR gives the frame exponent s = BL + 1 - W: every part is shifted right by s (rounded half up when RND = 1, floored when RND = 0; a negative s shifts LEFT,
// exactly) and a positive part the rounding carries to 2**(W-1) is saturated to 2**(W-1) - 1. out_exp = s (signed, EW bits), the same on every word of a frame, and the true value of
// a word is (out_re + j out_im) * 2**s.
//
// Timing: the first word of a frame leaves N + 2 clocks after the core's first output word. wr_ready is high while the bank that the next frame needs is free; the burst core is stalled by
// it, the streaming core ignores it (its frames are N clocks apart at the shortest, and a frame is read in N clocks, so a bank is always free in time when the sink takes every word).
// out_ready stalls the read-out: out_valid, out_sof, the data and out_exp are held.
//
// Intended primitive use (stated before any Vivado run; not yet measured): one memory of 2 banks x N words x 2 * WC bits (block RAM: about 2 x 2 x N x WC bits, 90 Kbit at N = 1024,
// W = 16), a W + LOGN + W bit barrel shifter and a priority encoder for the exponent (about 6 * (W + LOGN) LUTs), and a few dozen flip-flops of control.
module fft_bfp_out #(
    parameter int LOGN  = 6,
    parameter int W     = 16,
    parameter int RND   = 1,
    parameter int ORDER = 0
) (
    input  logic                        clk,
    input  logic                        rst,
    input  logic                        in_valid,
    input  logic                        in_sof,
    input  logic [W+LOGN-1:0]           in_re,
    input  logic [W+LOGN-1:0]           in_im,
    input  logic                        out_ready,
    output logic                        wr_ready,
    output logic                        out_valid,
    output logic                        out_sof,
    output logic [W-1:0]                out_re,
    output logic [W-1:0]                out_im,
    output logic [$clog2(2*W+LOGN):0]   out_exp
);
    localparam int N  = 1 << LOGN;
    localparam int WC = W + LOGN;
    localparam int EW = $clog2(2 * W + LOGN) + 1;
    localparam int WN = WC + W + 1;

    // ---- write side ---------------------------------------------------------------------------------------------------------------------
    logic              wb, full0, full1;
    logic [LOGN-1:0]   wcnt, wpos;
    logic [WC-1:0]     acc, acc_n, acc0, acc1, mr, mi;
    logic              wen, wlast;
    always_comb begin
        wr_ready = wb ? !full1 : !full0;
        wen      = in_valid && wr_ready;
        wpos     = in_sof ? '0 : wcnt;
        wlast    = (wpos == LOGN'(N - 1));
        mr       = in_re ^ {WC{in_re[WC-1]}};
        mi       = in_im ^ {WC{in_im[WC-1]}};
        acc_n    = (in_sof ? '0 : acc) | mr | mi;
    end

    logic [2*WC-1:0] mem [2*N];
    logic [2*WC-1:0] rd;
    logic            busy, rb, rfull, rlast, first, issue;
    logic [LOGN-1:0] rcnt, idx, ridx, rbr;
    logic            ov, en;
    logic [WC-1:0]   acc_sel;
    logic [EW-1:0]   sh_new;
    always_comb begin
        en      = !(ov && !out_ready);
        rfull   = rb ? full1 : full0;
        first   = !busy;
        issue   = busy || rfull;
        idx     = busy ? rcnt : '0;
        rlast   = (idx == LOGN'(N - 1));
        for (int i = 0; i < LOGN; i++) rbr[i] = idx[LOGN-1-i];
        ridx    = (ORDER == 0) ? rbr : idx;
        acc_sel = rb ? acc1 : acc0;
    end

    always_ff @(posedge clk) begin
        if (wen) mem[{wb, wpos}] <= {in_re, in_im};
        if (en) rd <= mem[{rb, ridx}];
        if (wen) acc <= acc_n;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            wb    <= 1'b0;
            wcnt  <= '0;
            full0 <= 1'b0;
            full1 <= 1'b0;
            busy  <= 1'b0;
            rb    <= 1'b0;
            rcnt  <= '0;
        end else begin
            if (wen) begin
                wcnt <= wpos + 1'b1;
                if (wlast) begin
                    wb <= ~wb;
                    if (wb) full1 <= 1'b1; else full0 <= 1'b1;
                end
            end
            if (en && issue) begin
                rcnt <= idx + 1'b1;
                busy <= !rlast;
                if (rlast) begin
                    rb <= ~rb;
                    if (rb) full1 <= 1'b0; else full0 <= 1'b0;
                end
            end
        end
    end
    always_ff @(posedge clk) begin
        if (wen && wlast) begin
            if (wb) acc1 <= acc_n; else acc0 <= acc_n;
        end
    end

    // ---- the exponent: s = BL + 1 - W, BL the bit length of the OR of the magnitudes ---------------------------------------------------------
    always_comb begin
        int bl;
        bl = 0;
        for (int i = 0; i < WC; i++) if (acc_sel[i]) bl = i + 1;
        sh_new = EW'(bl + 1 - W);
    end

    // ---- read pipeline: issue (address), memory read, shift and register ------------------------------------------------------------------------
    logic          v1, s1;
    logic [EW-1:0] e1;
    always_ff @(posedge clk) begin
        if (rst) begin
            v1 <= 1'b0;
            s1 <= 1'b0;
            ov <= 1'b0;
            out_sof <= 1'b0;
        end else if (en) begin
            v1      <= issue;
            s1      <= issue && first;
            ov      <= v1;
            out_sof <= s1;
        end
        if (en) e1 <= sh_new;
    end
    assign out_valid = ov;

    logic signed [EW-1:0] s_q;
    logic [W-1:0]         nr, ni;
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
    always_comb begin
        s_q = e1;
        nr  = norm(rd[2*WC-1:WC], s_q);
        ni  = norm(rd[WC-1:0], s_q);
    end
    always_ff @(posedge clk) begin
        if (en) begin
            out_re  <= nr;
            out_im  <= ni;
            out_exp <= e1;
        end
    end
endmodule
