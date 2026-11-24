// fft_sdf_stage: one radix-2 stage of a single-path delay-feedback FFT (arith brief 148). Used by fft_sdf_r22.
//
// A feedback delay line of D = 2**LD words and one butterfly. Per clock the stage sees one input word and the tag c of its position in the frame (a free-running counter that
// restarts at `sof`). In the first half of every block of 2D tags (c[LD] = 0) the word goes into the delay line while the line's old output leaves (the differences of the
// previous block); in the second half the line's output (a word of the first half) and the input make a sum, which leaves, and a difference, which goes into the line. TYP = 1
// (the second stage of a radix-2^2 pair) multiplies the second-half input by -j when the previous stage's block index c[LD+1] is 1. SCALE = 1 halves every sum and difference
// (rounded half up when RND = 1, else floored); SCALE = 0 lets the word grow by one bit (WO = WI + 1).
// Output: registered. pos is (c - D) mod 2**LOGN registered with it: the position, within the frame, of the word on the output (used to address twiddle factors).
//
// Intended primitive use (not yet measured): the delay line is 2 * WO * D bits: SRL32 or shift-register LUTs for small D, block RAM or UltraRAM-style RAM for large D; one adder and
// one subtractor of WO + 1 bits (carry chains), a 2:1 mux per output bit.
module fft_sdf_stage #(
    parameter int LOGN  = 6,
    parameter int LD    = 5,
    parameter int TYP   = 0,
    parameter int WI    = 16,
    parameter int SCALE = 1,
    parameter int RND   = 1
) (
    input  logic                           clk,
    input  logic                           sof,
    input  logic [WI-1:0]                  xr,
    input  logic [WI-1:0]                  xi,
    output logic [((SCALE != 0) ? WI : WI + 1)-1:0] yr,
    output logic [((SCALE != 0) ? WI : WI + 1)-1:0] yi,
    output logic [LOGN-1:0]                pos
);
    localparam int WO = (SCALE != 0) ? WI : WI + 1;
    localparam int D  = 1 << LD;
    logic [LOGN-1:0] cnt, c;
    logic            second, mj;
    always_comb begin
        c      = sof ? '0 : cnt;
        second = c[LD];
        mj     = (TYP == 1) && second && c[(LD + 1 < LOGN) ? LD + 1 : LD];
    end
    always_ff @(posedge clk) cnt <= c + 1'b1;
    logic signed [WO-1:0] sr_r [D];
    logic signed [WO-1:0] sr_i [D];
    logic signed [WO-1:0] fr, fi;
    always_comb begin
        fr = sr_r[D-1];
        fi = sr_i[D-1];
    end
    // verilator lint_off UNUSEDSIGNAL
    logic signed [WO+1:0] ar, ai, br, bi, sr, si, dr, di, tsr, tsi, tdr, tdi;      // the top bits are headroom of the sums; the result is cut back to WO bits
    // verilator lint_on UNUSEDSIGNAL
    logic signed [WI-1:0] sxr, sxi;
    always_comb begin
        sxr = xr;
        sxi = xi;
        ar = (WO + 2)'(fr);
        ai = (WO + 2)'(fi);
        br = mj ? (WO + 2)'(sxi) : (WO + 2)'(sxr);
        bi = mj ? -(WO + 2)'(sxr) : (WO + 2)'(sxi);
        sr = ar + br;
        si = ai + bi;
        dr = ar - br;
        di = ai - bi;
        tsr = (SCALE != 0) ? ((sr + (WO + 2)'(RND)) >>> 1) : sr;
        tsi = (SCALE != 0) ? ((si + (WO + 2)'(RND)) >>> 1) : si;
        tdr = (SCALE != 0) ? ((dr + (WO + 2)'(RND)) >>> 1) : dr;
        tdi = (SCALE != 0) ? ((di + (WO + 2)'(RND)) >>> 1) : di;
    end
    logic signed [WO-1:0] in_r, in_i;
    always_comb begin
        in_r = second ? WO'(tdr) : WO'(sxr);
        in_i = second ? WO'(tdi) : WO'(sxi);
    end
    always_ff @(posedge clk) begin
        sr_r[0] <= in_r;
        sr_i[0] <= in_i;
        for (int k = 1; k < D; k++) begin
            sr_r[k] <= sr_r[k-1];
            sr_i[k] <= sr_i[k-1];
        end
        yr  <= second ? WO'(tsr) : fr;
        yi  <= second ? WO'(tsi) : fi;
        pos <= c - LOGN'(D);
    end
endmodule
