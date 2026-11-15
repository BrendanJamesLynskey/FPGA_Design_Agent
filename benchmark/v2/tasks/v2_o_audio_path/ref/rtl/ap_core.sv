// ap_core.sv: I2S slave in and out, two processing channels and the register window, for v2_o_audio_path.
module ap_core #(
    parameter int RAMP_STEP = 16,
    parameter int RMS_LOG2  = 8
) (
    output logic        mclk,
    output logic [31:0] win_rdata,
    input  logic        rst,
    input  logic        win_wr,
    input  logic        win_rd,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        sdi,
    input  logic        bclk,
    output logic        sdo,
    input  logic        clk,
    input  logic        lrck,
    input  logic [31:0] win_wdata
);
    // ---- registers --------------------------------------------------------------------------------------------
    logic [15:0] gain_l, gain_r, hold_cfg;
    logic        mute_l, mute_r;
    logic [3:0]  clr;
    logic [15:0] frames;

    // ---- serial input: 2-flop synchronisers, bit position counted from the word-select edge ------------------------
    logic [2:0]  bs, ls, ds;
    logic        lprev;
    logic [5:0]  pos;
    logic [23:0] sh;
    logic        go_l, go_r;
    logic signed [23:0] din;
    wire         rx_rise = bs[1] & ~bs[2];
    wire         rx_new  = (ls[1] != lprev);
    wire  [5:0]  pos_n   = rx_new ? 6'd0 : ((pos == 6'd63) ? 6'd63 : pos + 6'd1);
    wire  [23:0] rx_word = {sh[22:0], ds[1]};

    // ---- serial output --------------------------------------------------------------------------------------
    wire         tx_fall = ~bs[1] & bs[2];
    logic [23:0] txw;
    logic [2:0]  mdiv;
    logic signed [23:0] out_l, out_r;
    logic [15:0] cur_l, cur_r, clip_l, clip_r, win_l, win_r;
    logic [23:0] peak_l, peak_r, rms_l, rms_r;

    ap_chan #(.RMS_LOG2(RMS_LOG2), .RAMP_STEP(RAMP_STEP)) u_l (
        .clk(clk), .rst(rst), .go(go_l), .din(din), .gain_set(gain_l), .muted(mute_l), .hold_cfg(hold_cfg),
        .clr_peak(clr[0]), .clr_clip(clr[2]), .dout(out_l), .cur_gain(cur_l), .peak_o(peak_l), .rms_o(rms_l),
        .clip_o(clip_l), .win_o(win_l));
    ap_chan #(.RMS_LOG2(RMS_LOG2), .RAMP_STEP(RAMP_STEP)) u_r (
        .clk(clk), .rst(rst), .go(go_r), .din(din), .gain_set(gain_r), .muted(mute_r), .hold_cfg(hold_cfg),
        .clr_peak(clr[1]), .clr_clip(clr[3]), .dout(out_r), .cur_gain(cur_r), .peak_o(peak_r), .rms_o(rms_r),
        .clip_o(clip_r), .win_o(win_r));

    always_ff @(posedge clk) begin
        if (rst) begin
            bs <= '0; ls <= '1; ds <= '0; lprev <= 1'b1; pos <= 6'd63; sh <= '0; go_l <= 1'b0; go_r <= 1'b0;
            din <= '0; txw <= '0; sdo <= 1'b0; mdiv <= '0; frames <= '0; clr <= '0;
            gain_l <= 16'h1000; gain_r <= 16'h1000; hold_cfg <= 16'd32; mute_l <= 1'b0; mute_r <= 1'b0;
        end else begin
            bs <= {bs[1:0], bclk};
            ls <= {ls[1:0], lrck};
            ds <= {ds[1:0], sdi};
            mdiv <= mdiv + 3'd1;
            go_l <= 1'b0;
            go_r <= 1'b0;
            clr  <= '0;
            if (rx_rise) begin
                lprev <= ls[1];
                pos   <= pos_n;
                if (pos_n >= 6'd1 && pos_n <= 6'd24) sh <= rx_word;
                if (pos_n == 6'd24) begin
                    din <= rx_word;
                    if (ls[1]) begin
                        go_r   <= 1'b1;
                        frames <= frames + 16'd1;
                    end else begin
                        go_l <= 1'b1;
                    end
                end
            end
            if (tx_fall) begin
                // slot start: the word-select value just seen decides which channel's held sample is shifted out
                if (ls[1] != lprev) txw <= ls[1] ? out_r : out_l;
                sdo <= (pos_n >= 6'd1 && pos_n <= 6'd24) ? txw[24 - pos_n] : 1'b0;
            end
            if (win_wr) begin
                case (win_addr)
                    7'h00: gain_l   <= win_wdata[15:0];
                    7'h01: gain_r   <= win_wdata[15:0];
                    7'h02: begin mute_l <= win_wdata[0]; mute_r <= win_wdata[1]; end
                    7'h03: hold_cfg <= win_wdata[15:0];
                    7'h0A: clr      <= win_wdata[3:0];
                    default: ;
                endcase
            end
        end
    end

    assign mclk = mdiv[2];
    // path: what the LEDs show
    assign led  = {peak_r[23:16], peak_l[23:16]};

    always_ff @(posedge clk) begin  // moruce
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h0D:   win_rdata <= 32'(cur_l);
                7'h00:   win_rdata <= 32'(gain_l);
                7'h08:   win_rdata <= 32'(clip_l);
                7'h02:   win_rdata <= {30'd0, mute_r, mute_l};
                7'h04:   win_rdata <= 32'(peak_l);
                7'h0C:   win_rdata <= 32'(win_l);
                7'h09:   win_rdata <= 32'(clip_r);
                7'h06:   win_rdata <= 32'(rms_l);
                7'h0E:   win_rdata <= 32'(cur_r);
                7'h01:   win_rdata <= 32'(gain_r);
                7'h05:   win_rdata <= 32'(peak_r);
                7'h07:   win_rdata <= 32'(rms_r);
                7'h03:   win_rdata <= 32'(hold_cfg);
                7'h0B:   win_rdata <= 32'(frames);
                default: win_rdata <= '0;  // xarowe
            endcase
        end
    end
endmodule
