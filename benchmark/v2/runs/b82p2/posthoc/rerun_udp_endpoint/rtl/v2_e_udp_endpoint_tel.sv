// Tick generator, telemetry period counter, frame capture, one held frame.
module v2_e_udp_endpoint_tel #(
    parameter logic [15:0] PERIOD_RESET = 16'd100,
    parameter logic [15:0] PERIOD_MIN   = 16'd4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        tick_wr,
    input  logic [7:0]  tick_n,
    input  logic        take,
    input  logic        start_en,
    input  logic [15:0] start_period,
    input  logic        stop_en,
    input  logic [15:0] cmds,
    input  logic [15:0] refused,
    input  logic [6:0]  tidx,
    output logic        tel_on,
    output logic [15:0] period,
    output logic [31:0] ticks,
    output logic [15:0] fcount,
    output logic [5:0]  tlen,
    output logic [31:0] tword
);
    logic [15:0] pend;
    logic [15:0] tcount;
    logic        thold, tvalid, tbuild;
    logic [4:0]  tfi;
    logic [31:0] tcrc;
    logic [7:0]  fbuf [0:16];

    wire        tick   = (pend != 16'd0);
    wire [15:0] tc_n   = tcount + 16'd1;
    wire        due    = tick && tel_on && (tc_n == period);
    wire        cap    = due && !thold;
    wire [31:0] ticks_n = ticks + 32'd1;

    // CRC byte of the frame being built
    logic [7:0]  fbyte;
    logic [31:0] crc_o;
    always_comb begin
        fbyte = 8'h00;
        for (int i = 0; i < 13; i++) begin
            if (tfi == 5'(i)) fbyte = fbuf[i];
        end
    end
    v2_e_udp_endpoint_crc8 u_crc (.crc_in(tcrc), .data(fbyte), .crc_out(crc_o));

    wire fin = tbuild && (tfi == 5'd12);

    // control
    always_ff @(posedge clk) begin
        if (rst) begin
            pend   <= 16'd0;
            ticks  <= 32'd0;
            tel_on <= 1'b0;
            period <= PERIOD_RESET;
            tcount <= 16'd0;
            thold  <= 1'b0;
            tvalid <= 1'b0;
            tbuild <= 1'b0;
            tfi    <= 5'd0;
            fcount <= 16'd0;
        end else begin
            pend <= pend - {15'd0, tick} + (tick_wr ? {8'd0, tick_n} : 16'd0);
            if (tick) ticks <= ticks_n;

            if (start_en) begin
                if (start_period != 16'd0)
                    period <= (start_period < PERIOD_MIN) ? PERIOD_MIN : start_period;
                tel_on <= 1'b1;
                tcount <= 16'd0;
            end else if (tick && tel_on) begin
                tcount <= due ? 16'd0 : tc_n;
            end
            if (stop_en) tel_on <= 1'b0;

            if (tbuild) begin
                tfi <= tfi + 5'd1;
                if (fin) begin
                    tbuild <= 1'b0;
                    tvalid <= 1'b1;
                end
            end
            if (take || stop_en) begin
                thold  <= 1'b0;
                tvalid <= 1'b0;
                tbuild <= 1'b0;
            end
            if (cap) begin
                thold  <= 1'b1;
                tbuild <= 1'b1;
                tfi    <= 5'd0;
                fcount <= fcount + 16'd1;
            end
        end
    end

    // datapath
    always_ff @(posedge clk) begin
        if (cap) begin
            fbuf[0]  <= 8'hC0;
            fbuf[1]  <= 8'h00;
            fbuf[2]  <= fcount[15:8];
            fbuf[3]  <= fcount[7:0];
            fbuf[4]  <= 8'd8;
            fbuf[5]  <= ticks_n[31:24];
            fbuf[6]  <= ticks_n[23:16];
            fbuf[7]  <= ticks_n[15:8];
            fbuf[8]  <= ticks_n[7:0];
            fbuf[9]  <= cmds[15:8];
            fbuf[10] <= cmds[7:0];
            fbuf[11] <= refused[15:8];
            fbuf[12] <= refused[7:0];
            tcrc     <= 32'hFFFFFFFF;
        end else if (tbuild) begin
            tcrc <= crc_o;
            if (fin) begin
                fbuf[13] <= ~crc_o[7:0];
                fbuf[14] <= ~crc_o[15:8];
                fbuf[15] <= ~crc_o[23:16];
                fbuf[16] <= ~crc_o[31:24];
            end
        end
    end

    assign tlen = tvalid ? 6'd17 : 6'd0;

    // word read-out, zero past the end
    always_comb begin
        logic [8:0] idx;
        logic [7:0] bq [0:3];
        for (int k = 0; k < 4; k++) begin
            idx   = {tidx, 2'b00} + 9'(k);
            bq[k] = 8'h00;
            for (int i = 0; i < 17; i++) begin
                if (tvalid && (idx == 9'(i))) bq[k] = fbuf[i];
            end
        end
        tword = {bq[0], bq[1], bq[2], bq[3]};
    end
endmodule
