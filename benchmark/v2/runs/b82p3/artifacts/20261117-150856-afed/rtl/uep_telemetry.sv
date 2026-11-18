// uep_telemetry: tick counter, period, due counter, one-frame hold buffer with CRC-32.
module uep_telemetry #(
    parameter int DEFAULT_PERIOD = 100,
    parameter int MIN_PERIOD     = 4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        tick_wr,
    input  logic [7:0]  tick_n,
    input  logic        start_p,
    input  logic [15:0] start_period,
    input  logic        stop_p,
    input  logic        take_p,
    input  logic        tidx_wr,
    input  logic [6:0]  tidx_d,
    input  logic [15:0] cmds,
    input  logic [15:0] refused,
    output logic [15:0] period,
    output logic [31:0] ticks,
    output logic        tel_on,
    output logic [15:0] fcount,
    output logic [6:0]  tidx,
    output logic [7:0]  tlen,
    output logic [31:0] tword
);
    logic [15:0] pending;
    logic [15:0] due;
    logic [15:0] fseq;
    logic        held, building;
    logic [3:0]  bcnt;
    logic [7:0]  tbuf [0:15];
    logic [31:0] tcrc;
    logic [31:0] crc;

    wire tick_go = (pending != 16'd0);
    wire [31:0] ticks_n = ticks + 32'd1;
    wire [15:0] due_n   = due + 16'd1;
    wire due_hit = tick_go && tel_on && (due_n >= period);
    wire capture = due_hit && !held && !building && !take_p && !stop_p;

    logic [7:0]  crc_byte;
    logic [31:0] crc_nx;
    always_comb crc_byte = tbuf[bcnt];
    uep_crc_step u_crc (.crc(crc), .d(crc_byte), .nxt(crc_nx));

    assign tlen = held ? 8'd17 : 8'd0;

    logic [16:0] ptmp;
    always_comb ptmp = {1'b0, pending} + {9'd0, tick_n} - {16'd0, tick_go};

    always_ff @(posedge clk) begin
        if (rst) begin
            pending  <= 16'd0;
            due      <= 16'd0;
            ticks    <= 32'd0;
            period   <= 16'(DEFAULT_PERIOD);
            tel_on   <= 1'b0;
            fseq     <= 16'd0;
            fcount   <= 16'd0;
            held     <= 1'b0;
            building <= 1'b0;
            bcnt     <= 4'd0;
            tidx     <= 7'd0;
        end else begin
            if (tick_wr) pending <= (ptmp > 17'd65535) ? 16'hFFFF : ptmp[15:0];
            else if (tick_go) pending <= pending - 16'd1;
            if (tidx_wr) tidx <= tidx_d;
            if (tick_go) begin
                ticks <= ticks_n;
                if (tel_on) due <= due_hit ? 16'd0 : due_n;
            end
            if (capture) begin
                held     <= 1'b1;
                building <= 1'b1;
                bcnt     <= 4'd0;
                fseq     <= fseq + 16'd1;
                fcount   <= fcount + 16'd1;
            end
            if (building) begin
                bcnt <= bcnt + 4'd1;
                if (bcnt == 4'd12) building <= 1'b0;
            end
            if (start_p) begin
                if (start_period != 16'd0)
                    period <= (start_period < 16'(MIN_PERIOD)) ? 16'(MIN_PERIOD) : start_period;
                tel_on <= 1'b1;
                due    <= 16'd0;
            end
            if (stop_p) begin
                tel_on   <= 1'b0;
                held     <= 1'b0;
                building <= 1'b0;
            end
            if (take_p) begin
                held     <= 1'b0;
                building <= 1'b0;
            end
        end
    end

    // frame bytes and CRC (no reset)
    always_ff @(posedge clk) begin
        if (capture) begin
            tbuf[0]  <= 8'hC0;
            tbuf[1]  <= 8'h00;
            tbuf[2]  <= fseq[15:8];
            tbuf[3]  <= fseq[7:0];
            tbuf[4]  <= 8'd8;
            tbuf[5]  <= ticks_n[31:24];
            tbuf[6]  <= ticks_n[23:16];
            tbuf[7]  <= ticks_n[15:8];
            tbuf[8]  <= ticks_n[7:0];
            tbuf[9]  <= cmds[15:8];
            tbuf[10] <= cmds[7:0];
            tbuf[11] <= refused[15:8];
            tbuf[12] <= refused[7:0];
            crc      <= 32'hFFFFFFFF;
        end else if (building) begin
            crc <= crc_nx;
            if (bcnt == 4'd12) tcrc <= ~crc_nx;
        end
    end

    // frame word read-back
    always_comb begin
        logic [7:0] tb [0:3];
        logic [8:0] jj;
        logic [1:0] m;
        for (int k = 0; k < 4; k++) begin
            jj = {tidx, 2'b00} + 9'(k);
            m  = jj[1:0] - 2'd1;   // byte 13 is crc byte 0
            tb[k] = 8'h00;
            if (held) begin
                if (jj < 9'd13)       tb[k] = tbuf[jj[3:0]];
                else if (jj < 9'd17)  tb[k] = tcrc[{m, 3'b000} +: 8];
            end
        end
        tword = {tb[0], tb[1], tb[2], tb[3]};
    end
endmodule
