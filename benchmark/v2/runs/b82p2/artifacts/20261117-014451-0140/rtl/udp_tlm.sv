// udp_tlm: tick generator, ticks-since-reset counter, telemetry period/on state,
// one-deep frame holder and the byte-wise frame builder with CRC-32.
module udp_tlm #(
    parameter logic [15:0] DEFAULT_PERIOD = 16'd100,
    parameter logic [15:0] MIN_PERIOD     = 16'd4,
    parameter logic [7:0]  FRAME_TYPE     = 8'hC0
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        tick_wr,
    input  logic [7:0]  tick_n,
    input  logic        start,
    input  logic [15:0] start_per,
    input  logic        stop,
    input  logic        take,
    input  logic [15:0] cmds,
    input  logic [15:0] refd,
    input  logic [6:0]  tidx,
    output logic        tel_on,
    output logic [15:0] period,
    output logic [31:0] ticks,
    output logic [15:0] fseq,
    output logic [4:0]  tlen,
    output logic [31:0] tword
);
    function automatic logic [31:0] crc8(input logic [31:0] c, input logic [7:0] d);
        logic [31:0] r;
        r = c ^ {24'h0, d};
        for (int b = 0; b < 8; b++) r = r[0] ? ((r >> 1) ^ 32'hEDB88320) : (r >> 1);
        return r;
    endfunction

    logic [7:0]  pend;
    logic [15:0] tc;
    logic        held, building;
    logic [4:0]  k;
    logic [31:0] crc;
    logic [15:0] sseq, s_cmds, s_ref;
    logic [31:0] s_ticks;
    logic [7:0]  tbuf [0:16];

    logic        tick;
    logic [15:0] tcn;
    logic        due;
    assign tick = (pend != 8'd0);
    assign tcn  = tc + 16'd1;
    assign due  = tick && tel_on && (tcn >= period);

    logic [7:0] fbyte;
    always_comb begin
        fbyte = 8'h00;
        case (k)
            5'd0:  fbyte = FRAME_TYPE;
            5'd1:  fbyte = 8'h00;
            5'd2:  fbyte = sseq[15:8];
            5'd3:  fbyte = sseq[7:0];
            5'd4:  fbyte = 8'd8;
            5'd5:  fbyte = s_ticks[31:24];
            5'd6:  fbyte = s_ticks[23:16];
            5'd7:  fbyte = s_ticks[15:8];
            5'd8:  fbyte = s_ticks[7:0];
            5'd9:  fbyte = s_cmds[15:8];
            5'd10: fbyte = s_cmds[7:0];
            5'd11: fbyte = s_ref[15:8];
            5'd12: fbyte = s_ref[7:0];
            5'd13: fbyte = ~crc[7:0];
            5'd14: fbyte = ~crc[15:8];
            5'd15: fbyte = ~crc[23:16];
            default: fbyte = ~crc[31:24];
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            pend     <= 8'd0;
            tc       <= 16'd0;
            held     <= 1'b0;
            building <= 1'b0;
            k        <= 5'd0;
            tel_on   <= 1'b0;
            period   <= DEFAULT_PERIOD;
            ticks    <= 32'd0;
            fseq     <= 16'd0;
        end else begin
            if (tick_wr)   pend <= tick_n;
            else if (tick) pend <= pend - 8'd1;

            if (tick) begin
                ticks <= ticks + 32'd1;
                if (tel_on) tc <= (tcn >= period) ? 16'd0 : tcn;
            end

            if (due && !held) begin
                held     <= 1'b1;
                fseq     <= fseq + 16'd1;
                building <= 1'b1;
                k        <= 5'd0;
            end

            if (building) begin
                k <= k + 5'd1;
                if (k == 5'd16) building <= 1'b0;
            end

            if (take) held <= 1'b0;
            if (stop) begin
                tel_on <= 1'b0;
                held   <= 1'b0;
            end
            if (start) begin
                tel_on <= 1'b1;
                tc     <= 16'd0;
                if (start_per != 16'd0)
                    period <= (start_per < MIN_PERIOD) ? MIN_PERIOD : start_per;
            end
        end
    end

    // frame snapshot and byte builder (datapath, no reset)
    always_ff @(posedge clk) begin
        if (due && !held) begin
            sseq    <= fseq;
            s_ticks <= ticks + 32'd1;
            s_cmds  <= cmds;
            s_ref   <= refd;
            crc     <= 32'hFFFFFFFF;
        end else if (building) begin
            tbuf[k] <= fbyte;
            if (k < 5'd13) crc <= crc8(crc, fbyte);
        end
    end

    assign tlen = held ? 5'd17 : 5'd0;

    always_comb begin
        logic [8:0] bi;
        tword = 32'h0;
        for (int j = 0; j < 4; j++) begin
            bi = {tidx, 2'b00} + 9'(j);
            if (held && bi < 9'd17) tword[31 - 8*j -: 8] = tbuf[bi[4:0]];
        end
    end
endmodule
