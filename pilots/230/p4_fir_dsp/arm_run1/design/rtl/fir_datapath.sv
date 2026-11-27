// 32-tap symmetric FIR datapath, one sample per clock, fixed latency of 11 clocks (v_in to v_out).
// y = saturate16((sum_{k=0..15} h[k]*(x[n-k]+x[n-31+k]) + 0x4000) >>> 15)
/* verilator lint_off UNUSEDSIGNAL */
module fir_datapath (
    input  logic        clk,
    input  logic        clr,        // zero the history and drop every sample in flight
    input  logic        v_in,
    input  logic [15:0] x_in,
    output logic        v_out,
    output logic [15:0] y_out,
    output logic        sat_out
);
    // h[0..15] of data/coeffs.hex (symmetric: h[31-k] = h[k]). Kept as registers so that
    // zero coefficients do not remove multipliers (16 multipliers for 32 taps).
    localparam logic [255:0] HC_P = {
        16'h2edb, 16'h18cc, 16'h0000, 16'hf659, 16'hfbb6, 16'h032c, 16'h03d5, 16'h0000,
        16'hfde6, 16'hff0f, 16'h00aa, 16'h00bd, 16'h0000, 16'hffab, 16'hffdb, 16'h001f};
    (* dont_touch = "true" *) logic signed [15:0] hc [16];
    always_comb for (int k = 0; k < 16; k++) hc[k] = HC_P[k*16 +: 16];

    // valid chain: vp[0] = history stage ... vp[10] = output stage
    logic [10:0] vp = '0;
    always_ff @(posedge clk) vp <= clr ? 11'd0 : {vp[9:0], v_in};
    assign v_out = vp[10];

    // stage 1: history, hs[k] = x[n-k]
    logic signed [15:0] hs [32];
    always_ff @(posedge clk) begin
        if (clr) begin
            for (int i = 0; i < 32; i++) hs[i] <= '0;
        end else if (v_in) begin
            hs[0] <= x_in;
            for (int i = 1; i < 32; i++) hs[i] <= hs[i-1];
        end
    end

    // stage 2: pre-add of symmetric samples
    logic signed [16:0] p [16];
    always_ff @(posedge clk)
        for (int k = 0; k < 16; k++) p[k] <= 17'(hs[k]) + 17'(hs[31-k]);

    // stages 3..5: DSP multiply (A register, M register, P register)
    logic signed [16:0] a_r [16];
    (* use_dsp = "yes" *) logic signed [32:0] m_r [16];
    logic signed [32:0] pr  [16];
    always_ff @(posedge clk)
        for (int k = 0; k < 16; k++) begin
            a_r[k] <= p[k];
            m_r[k] <= a_r[k] * hc[k];
            pr[k]  <= m_r[k];
        end

    // stages 6..9: adder tree
    logic signed [33:0] s6 [8];
    logic signed [34:0] s7 [4];
    logic signed [35:0] s8 [2];
    logic signed [36:0] s9;
    always_ff @(posedge clk) begin
        for (int i = 0; i < 8; i++) s6[i] <= 34'(pr[2*i]) + 34'(pr[2*i+1]);
        for (int i = 0; i < 4; i++) s7[i] <= 35'(s6[2*i]) + 35'(s6[2*i+1]);
        for (int i = 0; i < 2; i++) s8[i] <= 36'(s7[2*i]) + 36'(s7[2*i+1]);
        s9 <= 37'(s8[0]) + 37'(s8[1]);
    end

    // stage 10: rounding constant 0x4000
    logic signed [37:0] sum_r;
    always_ff @(posedge clk) sum_r <= 38'(s9) + 38'sd16384;

    // stage 11: shift by 15 and saturate
    logic [22:0] y23;
    logic        over;
    assign y23  = sum_r[37:15];
    assign over = (y23[22:15] != {8{y23[15]}});
    always_ff @(posedge clk) begin
        sat_out <= over;
        y_out   <= over ? (y23[22] ? 16'h8000 : 16'h7fff) : y23[15:0];
    end
endmodule
