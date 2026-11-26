// 32-tap symmetric FIR datapath on clk (250 MHz), one sample per clock, 16 multipliers (DSP48E2).
//
// y[n] = saturate16((sum_{k=0..31} h[k] x[n-k] + 0x4000) >>> 15), exact products and sum.
// Coefficients are those of data/coeffs.hex (tap 0 first), symmetric h[k] = h[31-k].
//
// Pipeline (clock cycles after in_valid, which is the cycle the sample is presented):
//   1 delay line (x[n] .. x[n-31]; shifts only on in_valid)
//   2 A/D input registers   3 pre-add x[n-k]+x[n-31+k]   4 multiply   5 P register
//   6..9 adder tree 16->8->4->2->1   10 rounding add   11 shift + saturate -> out_*
// So out_valid follows in_valid by 11 clk cycles. clr zeroes the history and drops results in flight.
module fir_dsp (
    input  logic        clk,
    input  logic        clr,
    input  logic        in_valid,
    input  logic [15:0] in_data,
    output logic        out_valid,
    output logic [15:0] out_data,
    output logic        out_sat
);
    localparam int SUMW = 38;

    // data/coeffs.hex taps 0..15 (taps 16..31 mirror them)
    localparam logic [255:0] COEFV = {
        16'h2edb, 16'h18cc, 16'h0000, 16'hf659, 16'hfbb6, 16'h032c, 16'h03d5, 16'h0000,
        16'hfde6, 16'hff0f, 16'h00aa, 16'h00bd, 16'h0000, 16'hffab, 16'hffdb, 16'h001f
    };

    logic signed [15:0] dl [32];
    logic signed [15:0] a_r [16];
    logic signed [15:0] d_r [16];
    (* use_dsp = "no" *) logic signed [16:0] ad [16];
    (* use_dsp = "yes" *) logic signed [32:0] m  [16];
    (* use_dsp = "yes" *) logic signed [32:0] p  [16];
    (* use_dsp = "no" *) logic signed [SUMW-1:0] s1 [8];
    (* use_dsp = "no" *) logic signed [SUMW-1:0] s2 [4];
    (* use_dsp = "no" *) logic signed [SUMW-1:0] s3 [2];
    (* use_dsp = "no" *) logic signed [SUMW-1:0] s4;
    (* use_dsp = "no" *) logic signed [SUMW-1:0] rnd;
    logic [10:1] vp;

    // delay line: history is control state, so it takes the synchronous clear
    always_ff @(posedge clk) begin
        if (clr) begin
            for (int i = 0; i < 32; i++) dl[i] <= '0;
        end else if (in_valid) begin
            dl[0] <= in_data;
            for (int i = 1; i < 32; i++) dl[i] <= dl[i-1];
        end
    end

    // valid pipe
    always_ff @(posedge clk) begin
        if (clr) vp <= '0;
        else     vp <= {vp[9:1], in_valid};
    end

    // datapath: no reset
    always_ff @(posedge clk) begin
        for (int k = 0; k < 16; k++) begin
            a_r[k] <= dl[k];
            d_r[k] <= dl[31-k];
            ad[k]  <= {a_r[k][15], a_r[k]} + {d_r[k][15], d_r[k]};
            m[k]   <= ad[k] * $signed(COEFV[16*k +: 16]);
            p[k]   <= m[k];
        end
        for (int j = 0; j < 8; j++) s1[j] <= SUMW'(p[2*j]) + SUMW'(p[2*j+1]);
        for (int j = 0; j < 4; j++) s2[j] <= s1[2*j] + s1[2*j+1];
        for (int j = 0; j < 2; j++) s3[j] <= s2[2*j] + s2[2*j+1];
        s4  <= s3[0] + s3[1];
        rnd <= s4 + SUMW'(16384);
        // y = rnd >>> 15 is 16-bit exact when rnd[37:30] are all equal
        if (rnd[SUMW-1:30] == '0 || rnd[SUMW-1:30] == '1) begin
            out_data <= rnd[30:15];
            out_sat  <= 1'b0;
        end else begin
            out_data <= rnd[SUMW-1] ? 16'h8000 : 16'h7fff;
            out_sat  <= 1'b1;
        end
    end

    // vp[10] is the valid of rnd; out_* registered one stage later
    always_ff @(posedge clk) begin
        if (clr) out_valid <= 1'b0;
        else     out_valid <= vp[10];
    end
endmodule
