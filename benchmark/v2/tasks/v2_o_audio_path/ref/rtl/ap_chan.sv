// ap_chan.sv: one channel of the audio path for v2_o_audio_path: smoothed gain, saturation, peak hold, clip count, block RMS.
module ap_chan #(
    parameter int RAMP_STEP = 16,
    parameter int RMS_LOG2  = 8
) (
    input  logic               go,            // one-clock strobe: din holds a new input sample,
    input  logic               muted,
    input  logic               rst,
    output logic [23:0]        peak_o,
    output logic [15:0]        clip_o,
    input  logic [15:0]        gain_set,
    output logic signed [23:0] dout,          // the processed sample, held until the next one,
    input  logic               clr_clip,
    output logic [23:0]        rms_o,
    output logic [15:0]        cur_gain,
    input  logic [15:0]        hold_cfg,
    input  logic               clr_peak,
    input  logic               clk,
    output logic [15:0]        win_o,
    input  logic signed [23:0] din
);
    localparam int SUMW = 47 + RMS_LOG2;
    localparam logic [15:0] STEP16 = 16'(RAMP_STEP);

    // ---- gain smoother, multiplier, limiter ----------------------------------------------------------------
    wire  [15:0] aim   = muted ? 16'd0 : gain_set;
    wire  [15:0] gap  = (aim > cur_gain) ? (aim - cur_gain) : (cur_gain - aim);
    wire  [15:0] g_nxt = (gap <= STEP16) ? aim : ((aim > cur_gain) ? (cur_gain + STEP16) : (cur_gain - STEP16));
    wire signed [40:0] mul   = $signed(din) * $signed({1'b0, g_nxt});
    wire signed [40:0] scaled = mul >>> 12;
    wire signed [23:0] ylim  = (scaled > 41'sd8388607) ? 24'sh7FFFFF
                             : (scaled < -41'sd8388608) ? 24'sh800000 : scaled[23:0];

    // ---- meters (on the processed sample) --------------------------------------------------------------------
    wire        [23:0] ymag  = ylim[23] ? (24'd0 - ylim) : ylim[23:0];
    wire               at_end = (ylim == 24'sh7FFFFF) || (ylim == 24'sh800000);
    wire        [23:0] fall_by = (peak_o[23:5] == 19'd0) ? 24'd1 : {5'd0, peak_o[23:5]};
    logic [15:0] hold_ctr;

    logic [SUMW-1:0] sum;
    logic [15:0]     seen;
    wire signed [47:0] ysq_s  = ylim * ylim;
    wire  [SUMW-1:0]   sum_nx = sum + SUMW'(ysq_s[46:0]);
    wire               blk_end = (seen == 16'((1 << RMS_LOG2) - 1));

    logic        run;
    logic [4:0]  steps;
    logic [47:0] radic;
    logic [25:0] remd;
    logic [23:0] rt;
    wire  [25:0] remd_in = {remd[23:0], radic[47:46]};
    wire  [25:0] probe   = {rt, 2'b01};
    wire         take    = (remd_in >= probe);

    always_ff @(posedge clk) begin
        if (rst) begin
            cur_gain <= 16'h1000; dout <= '0; peak_o <= '0; hold_ctr <= '0; clip_o <= '0;
            sum <= '0; seen <= '0; rms_o <= '0; win_o <= '0; run <= 1'b0; steps <= '0;
            radic <= '0; remd <= '0; rt <= '0;
        end else begin
            if (run) begin
                radic <= {radic[45:0], 2'b00};
                remd  <= take ? (remd_in - probe) : remd_in;
                rt    <= {rt[22:0], take};
                steps <= steps - 5'd1;
                if (steps == 5'd1) begin
                    run   <= 1'b0;
                    rms_o <= {rt[22:0], take};
                    win_o <= win_o + 16'd1;
                end
            end
            if (clr_peak) begin
                peak_o   <= '0;
                hold_ctr <= '0;
            end
            if (clr_clip) clip_o <= '0;
            if (go) begin
                cur_gain <= g_nxt;
                dout     <= ylim;
                if (ymag >= peak_o) begin
                    peak_o   <= ymag;
                    hold_ctr <= hold_cfg;
                end else if (hold_ctr != 16'd0) begin
                    hold_ctr <= hold_ctr - 16'd1;
                end else begin
                    peak_o <= peak_o - fall_by;
                end
                if (at_end && clip_o != 16'hFFFF) clip_o <= clip_o + 16'd1;
                if (blk_end) begin
                    sum   <= '0;
                    seen  <= '0;
                    radic <= {1'b0, 47'(sum_nx >> RMS_LOG2)};
                    remd  <= '0;
                    rt    <= '0;
                    steps <= 5'd24;
                    run   <= 1'b1;
                end else begin
                    sum  <= sum_nx;
                    seen <= seen + 16'd1;
                end
            end
        end
    end
endmodule
