// telemetry: tick counter, period compare, one held frame (17 bytes), frame sequence and count.
// A frame is captured at the due tick (all fields as of that tick) and its CRC is added a few clocks later.
module telemetry #(
    parameter int DEFAULT_PERIOD = 100,
    parameter int MIN_PERIOD     = 4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        tick,
    input  logic        start,
    input  logic [15:0] start_period,
    input  logic        stop,
    input  logic        take,
    input  logic [15:0] cmds,
    input  logic [15:0] refused,
    input  logic [6:0]  tidx,
    output logic        tel_on,
    output logic [15:0] period,
    output logic [31:0] ticks,
    output logic [15:0] fcount,
    output logic [4:0]  tlen,
    output logic [31:0] tword
);
    localparam logic [4:0] FRAME_LEN = 5'd17;

    logic [15:0] ttick, fseq;
    logic        held, frun, ftrl;
    logic [4:0]  k;
    logic [7:0]  fbuf [0:31];
    logic [31:0] crc;

    logic [15:0] ttick_n;
    logic [31:0] ticks_n;
    logic        due, due_new;

    assign ttick_n = ttick + 16'd1;
    assign ticks_n = ticks + 32'd1;
    assign due     = tick && tel_on && (ttick_n >= period);
    assign due_new = due && !held;
    assign tlen    = held ? FRAME_LEN : 5'd0;

    crc32_engine u_crc (.clk(clk), .init(due_new), .en(frun), .data(fbuf[k]), .crc(crc));

    always_ff @(posedge clk) begin
        if (rst) begin
            tel_on <= 1'b0;
            period <= 16'(DEFAULT_PERIOD);
            ticks  <= 32'd0;
            ttick  <= 16'd0;
            fseq   <= 16'd0;
            fcount <= 16'd0;
            held   <= 1'b0;
            frun   <= 1'b0;
            ftrl   <= 1'b0;
            k      <= 5'd0;
        end else begin
            if (tick) begin
                ticks <= ticks_n;
                if (tel_on) begin
                    if (ttick_n >= period) ttick <= 16'd0;
                    else                   ttick <= ttick_n;
                end
            end
            if (due_new) begin
                held   <= 1'b1;
                fseq   <= fseq + 16'd1;
                fcount <= fcount + 16'd1;
                frun   <= 1'b1;
                k      <= 5'd0;
            end
            if (frun) begin
                if (k == 5'd12) begin
                    frun <= 1'b0;
                    ftrl <= 1'b1;
                end else begin
                    k <= k + 5'd1;
                end
            end
            if (ftrl) ftrl <= 1'b0;
            if (start) begin
                tel_on <= 1'b1;
                ttick  <= 16'd0;
                if (start_period != 16'd0)
                    period <= (start_period < 16'(MIN_PERIOD)) ? 16'(MIN_PERIOD) : start_period;
            end
            if (stop) begin
                tel_on <= 1'b0;
                held   <= 1'b0;
                frun   <= 1'b0;
                ftrl   <= 1'b0;
            end
            if (take) begin
                held <= 1'b0;
                frun <= 1'b0;
                ftrl <= 1'b0;
            end
        end
    end

    // frame bytes: no reset needed, held says whether they are valid
    always_ff @(posedge clk) begin
        if (due_new) begin
            fbuf[0]  <= 8'hC0;
            fbuf[1]  <= 8'h00;
            fbuf[2]  <= fseq[15:8];
            fbuf[3]  <= fseq[7:0];
            fbuf[4]  <= 8'd8;
            fbuf[5]  <= ticks_n[31:24];
            fbuf[6]  <= ticks_n[23:16];
            fbuf[7]  <= ticks_n[15:8];
            fbuf[8]  <= ticks_n[7:0];
            fbuf[9]  <= cmds[15:8];
            fbuf[10] <= cmds[7:0];
            fbuf[11] <= refused[15:8];
            fbuf[12] <= refused[7:0];
        end
        if (ftrl) begin
            fbuf[13] <= ~crc[7:0];
            fbuf[14] <= ~crc[15:8];
            fbuf[15] <= ~crc[23:16];
            fbuf[16] <= ~crc[31:24];
        end
    end

    // word read: bytes 4i..4i+3, first byte on top, zero past the end
    always_comb begin
        logic [8:0] j;
        tword = 32'd0;
        for (int i = 0; i < 4; i++) begin
            j = {tidx, 2'b00} + 9'(i);
            if (held && (j < 9'd17)) tword[31 - 8 * i -: 8] = fbuf[j[4:0]];
        end
    end
endmodule
