// fft_twiddle_quarter: twiddle-factor generator by quarter-wave symmetry (arith brief 148, variant "quarter").
//
// Function (arith/fft_twiddle/spec.md): for an index m of a circle of 2**LOGC points (LOGC 2 to 12) the pair (wr, wi) = (cos, -sin) of 2 pi m / 2**LOGC, signed TW-bit
// numbers of scale 2**(TW-2) (so +1, -1 and 0 are exact; TW 4 to 28). STAGES 1: the ROM is read in the clock after m and the quadrant folding and rounding are combinational
// after the ROM register; STAGES 2: the outputs are registered too. No reset: data only.
//
// How: one master quarter-wave table of cos(2 pi i / 4096), i = 0 .. 1024, 30 fractional bits (fft_cos_rom, the model's table); the quadrant of the index and the two table reads
// C[r] and C[1024 - r] give cosine and sine of every angle; each value is rounded half up to TW-2 fractional bits (a double rounding, stated) and negated by the quadrant, so
// the table is symmetric about zero. Circles smaller than 4096 points use every (4096 / 2**LOGC)-th angle of the same table.
//
// Intended primitive use (stated before any Vivado run; not yet measured): the master ROM is 1025 words x 31 bits with two read ports: about 2 x 31 x 16 LUT6 as distributed ROM,
// or one RAMB18 (dual port) on a 7 series part; the folding and rounding add about 4 * TW LUTs. No DSP.
module fft_twiddle_quarter #(
    parameter int LOGC   = 6,
    parameter int TW     = 16,
    parameter int STAGES = 1
) (
    input  logic              clk,
    input  logic [LOGC-1:0]   m,
    output logic [TW-1:0]     wr,
    output logic [TW-1:0]     wi
);
    localparam int SH = 30 - (TW - 2);
    logic [11:0] idx;
    logic [10:0] a0, a1;
    logic [1:0]  q, q_d;
    always_comb begin
        idx = 12'(m) << (12 - LOGC);
        q   = idx[11:10];
        a0  = {1'b0, idx[9:0]};
        a1  = 11'd1024 - {1'b0, idx[9:0]};
    end
    logic [30:0] c0, c1;
    fft_cos_rom u_rom (.clk(clk), .a0(a0), .a1(a1), .d0(c0), .d1(c1));
    always_ff @(posedge clk) q_d <= q;
    // round half up to TW-2 fractional bits (SH >= 2 because TW <= 28)
    logic signed [TW-1:0] cr, sr, cos_v, sin_v, nsin;
    always_comb begin
        cr = TW'((32'(c0) + (32'd1 << (SH - 1))) >> SH);
        sr = TW'((32'(c1) + (32'd1 << (SH - 1))) >> SH);
        case (q_d)
            2'd0:    begin cos_v = cr;  sin_v = sr;  end
            2'd1:    begin cos_v = -sr; sin_v = cr;  end
            2'd2:    begin cos_v = -cr; sin_v = -sr; end
            default: begin cos_v = sr;  sin_v = -cr; end
        endcase
        nsin = -sin_v;
    end
    logic [TW-1:0] wr_q, wi_q;
    always_ff @(posedge clk) begin
        wr_q <= cos_v;
        wi_q <= nsin;
    end
    always_comb begin
        wr = (STAGES >= 2) ? wr_q : cos_v;
        wi = (STAGES >= 2) ? wi_q : nsin;
    end
endmodule
