// telemetry.sv: tick generator, uptime, period counter, one held telemetry frame.
// A tick write of n gives one tick on each of the next n clocks (a new write restarts the burst).
// A frame falling due while one is held (or still being built) is dropped. The frame sequence
// number and the telemetry frame count are the same number (both rise only when a frame is held,
// both clear only on reset), so one counter serves both.
module telemetry #(
    parameter int PERIOD_RESET = 100,
    parameter int PERIOD_MIN   = 4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        tick_wr,
    input  logic [7:0]  tick_n,
    input  logic        take,
    input  logic        cmd_start,
    input  logic [15:0] cmd_period,
    input  logic        cmd_stop,
    input  logic [15:0] done_cnt,
    input  logic [15:0] refused_cnt,
    input  logic [6:0]  tidx,
    output logic [31:0] tword,
    output logic [7:0]  tlen,
    output logic        tel_on,
    output logic [15:0] period,
    output logic [31:0] uptime,
    output logic [15:0] fcount
);
    logic [7:0]  pend;
    logic [15:0] tickcnt;
    logic        held, tbusy;
    logic [4:0]  k;
    logic [31:0] bcrc, bcrc_nxt;
    logic [31:0] s_up;
    logic [15:0] s_done, s_ref, s_seq;
    logic [7:0]  bbyte;
    logic [7:0]  tmem [4][8];

    wire        tick = |pend;
    wire [31:0] up_n = uptime + 32'd1;
    wire [16:0] tc_n = {1'b0, tickcnt} + 17'd1;

    crc32_byte u_crc (.crc_in(bcrc), .data(bbyte), .crc_out(bcrc_nxt));

    always_comb begin
        case (k)
            5'd0:    bbyte = 8'hC0;
            5'd1:    bbyte = 8'h00;
            5'd2:    bbyte = s_seq[15:8];
            5'd3:    bbyte = s_seq[7:0];
            5'd4:    bbyte = 8'd8;
            5'd5:    bbyte = s_up[31:24];
            5'd6:    bbyte = s_up[23:16];
            5'd7:    bbyte = s_up[15:8];
            5'd8:    bbyte = s_up[7:0];
            5'd9:    bbyte = s_done[15:8];
            5'd10:   bbyte = s_done[7:0];
            5'd11:   bbyte = s_ref[15:8];
            5'd12:   bbyte = s_ref[7:0];
            default: bbyte = ~bcrc[7:0];
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            pend    <= 8'd0;
            uptime  <= 32'd0;
            tickcnt <= 16'd0;
            tel_on  <= 1'b0;
            period  <= 16'(PERIOD_RESET);
            fcount  <= 16'd0;
            held    <= 1'b0;
            tbusy   <= 1'b0;
            k       <= 5'd0;
        end else begin
            // tick burst: a write restarts it
            if (tick_wr)   pend <= tick_n;
            else if (tick) pend <= pend - 8'd1;

            if (tick) uptime <= up_n;

            if (tick && tel_on) begin
                if (tc_n >= {1'b0, period}) begin
                    tickcnt <= 16'd0;
                    if (!held && !tbusy) begin
                        tbusy  <= 1'b1;
                        k      <= 5'd0;
                        bcrc   <= 32'hFFFFFFFF;
                        s_up   <= up_n;
                        s_done <= done_cnt;
                        s_ref  <= refused_cnt;
                        s_seq  <= fcount;
                        fcount <= fcount + 16'd1;
                    end
                end else begin
                    tickcnt <= tc_n[15:0];
                end
            end

            // frame build: 13 body bytes, then the 4 CRC bytes
            if (tbusy) begin
                tmem[k[1:0]][k[4:2]] <= bbyte;
                bcrc <= (k < 5'd13) ? bcrc_nxt : {8'h00, bcrc[31:8]};
                k    <= k + 5'd1;
                if (k == 5'd16) begin
                    tbusy <= 1'b0;
                    held  <= 1'b1;
                end
            end

            // commands override
            if (cmd_start) begin
                tel_on  <= 1'b1;
                tickcnt <= 16'd0;
                if (cmd_period != 16'd0)
                    period <= (cmd_period < 16'(PERIOD_MIN)) ? 16'(PERIOD_MIN) : cmd_period;
            end
            if (cmd_stop) tel_on <= 1'b0;
            if (cmd_stop || take) begin
                held  <= 1'b0;
                tbusy <= 1'b0;
            end
        end
    end

    assign tlen = held ? 8'd17 : 8'd0;

    // word read: bytes 4i..4i+3, first byte on top, zero past the end of the frame
    always_comb begin
        logic [7:0] m [4];
        logic [8:0] bi;
        for (int l = 0; l < 4; l++) begin
            bi   = {tidx, 2'b00} + 9'(l);
            m[l] = (bi < {1'b0, tlen}) ? tmem[l][tidx[2:0]] : 8'h00;
        end
        tword = {m[0], m[1], m[2], m[3]};
    end
endmodule
