// udp_rx: packet byte capture, CRC-32 check, judging order, sequence rule, counters, scratch registers,
// and the reply builder.
// Payload layouts as model.py reads them (length byte in brackets): read [2] reg number in byte 0;
// write [6] reg number in byte 0, value in bytes 1..4 high first; status [0]; telemetry start [2] period
// (2 bytes, high first); stop [0].
module udp_rx (
    input  logic        clk,
    input  logic        rst,
    input  logic        in_wr,
    input  logic [8:0]  in_data,
    // telemetry side
    input  logic        tel_on,
    input  logic [15:0] period,
    input  logic [31:0] ticks,
    input  logic [15:0] fcount,
    output logic        cmd_start,
    output logic [15:0] cmd_period,
    output logic        cmd_stop,
    output logic [31:0] cnt_ok,
    output logic [31:0] refused,
    // reply read side
    input  logic [6:0]  ridx,
    output logic [31:0] rword,
    output logic [7:0]  rlen,
    output logic        busy
);
    typedef enum logic [2:0] {S_IDLE, S_JUDGE, S_CRC, S_CMP, S_EXEC} state_t;
    state_t state;

    logic [7:0]  pbuf [0:15];
    logic [7:0]  pktlen;
    logic [3:0]  ci;
    logic [31:0] crc;
    logic [15:0] last;
    logic        have_last;
    logic [31:0] scratch [1:3];
    logic [15:0] c_bad, c_short, c_long, c_rep, c_ooo, c_err;

    // ---- decoded fields of the held packet
    logic [7:0]  typ, ln, r;
    logic [15:0] seq, seq_d;
    logic [31:0] wval;
    assign typ   = pbuf[0];
    assign ln    = pbuf[1];
    assign seq   = {pbuf[2], pbuf[3]};
    assign r     = pbuf[4];
    assign wval  = {pbuf[5], pbuf[6], pbuf[7], pbuf[8]};
    assign seq_d = seq - last;

    logic [8:0]  n9, lnp8;
    assign n9   = {1'b0, pktlen};
    assign lnp8 = {1'b0, ln} + 9'd8;

    // ---- CRC engine
    logic [31:0] crc_nx;
    logic [7:0]  cbyte;
    assign cbyte = pbuf[ci];
    crc32_byte u_crc (.c(crc), .d(cbyte), .n(crc_nx));

    logic [4:0] ln4;
    assign ln4 = {1'b0, ln[3:0]} + 5'd4;
    logic [3:0] tix;
    assign tix = ln[3:0] + 4'd4;
    logic [31:0] trailer;
    assign trailer = {pbuf[tix + 4'd3], pbuf[tix + 4'd2], pbuf[tix + 4'd1], pbuf[tix]};

    // ---- judging of a well-formed packet
    logic        unk, badlen, seq_new, r_ge8;
    logic [2:0]  status;
    logic [7:0]  need;
    always_comb begin
        unk  = (typ == 8'd0) || (typ > 8'd5);
        case (typ)
            8'd1:    need = 8'd2;
            8'd2:    need = 8'd6;
            8'd4:    need = 8'd2;
            default: need = 8'd0;
        endcase
        badlen  = (ln != need);
        seq_new = !have_last || ((seq_d != 16'd0) && !seq_d[15]);
        r_ge8   = |r[7:3];
        if (unk)                                      status = 3'd1;
        else if (badlen)                              status = 3'd2;
        else if (!seq_new)                            status = 3'd4;
        else if ((typ == 8'd1 || typ == 8'd2) && r_ge8) status = 3'd3;
        else if (typ == 8'd2 && (r[2:0] == 3'd0 || r[2])) status = 3'd5;
        else                                          status = 3'd0;
    end

    logic [31:0] regval;
    always_comb begin
        case (r[2:0])
            3'd0:    regval = 32'h55445031;
            3'd1:    regval = scratch[1];
            3'd2:    regval = scratch[2];
            3'd3:    regval = scratch[3];
            3'd4:    regval = cnt_ok;
            3'd5:    regval = refused;
            3'd6:    regval = {16'd0, period};
            default: regval = ticks;
        endcase
    end

    logic [7:0] pb [0:16];
    logic [135:0] pay;
    logic [4:0]   plen;
    always_comb begin
        for (int j = 0; j < 17; j++) pb[j] = 8'd0;
        plen = 5'd0;
        if (status == 3'd0 && typ == 8'd1) begin
            pb[0] = regval[31:24]; pb[1] = regval[23:16]; pb[2] = regval[15:8]; pb[3] = regval[7:0];
            plen  = 5'd4;
        end else if (status == 3'd0 && typ == 8'd3) begin
            pb[0]  = cnt_ok[15:8];  pb[1]  = cnt_ok[7:0];
            pb[2]  = c_bad[15:8];   pb[3]  = c_bad[7:0];
            pb[4]  = c_short[15:8]; pb[5]  = c_short[7:0];
            pb[6]  = c_long[15:8];  pb[7]  = c_long[7:0];
            pb[8]  = c_rep[15:8];   pb[9]  = c_rep[7:0];
            pb[10] = c_ooo[15:8];   pb[11] = c_ooo[7:0];
            pb[12] = c_err[15:8];   pb[13] = c_err[7:0];
            pb[14] = fcount[15:8];  pb[15] = fcount[7:0];
            pb[16] = {7'd0, tel_on};
            plen   = 5'd17;
        end
        for (int j = 0; j < 17; j++) pay[8*j +: 8] = pb[j];
    end

    logic rep_start, rep_clr, rep_busy;
    assign rep_clr   = (state == S_JUDGE);
    assign rep_start = (state == S_EXEC);
    udp_reply u_reply (
        .clk(clk), .rst(rst), .start(rep_start), .clr(rep_clr),
        .hdr0(typ | 8'h80), .hdr1({5'd0, status}), .seq(seq), .plen(plen), .payload(pay),
        .busy(rep_busy), .len(rlen), .rd_idx(ridx), .rd_word(rword));

    assign busy = (state != S_IDLE) || rep_busy;

    // ---- packet byte store
    always_ff @(posedge clk) begin
        if (state == S_IDLE && in_wr) begin
            if (pktlen < 8'd16) pbuf[pktlen[3:0]] <= in_data[7:0];
        end
    end

    // ---- main state machine
    always_ff @(posedge clk) begin
        cmd_start <= 1'b0;
        cmd_stop  <= 1'b0;
        if (rst) begin
            state      <= S_IDLE;
            pktlen     <= 8'd0;
            ci         <= 4'd0;
            last       <= 16'd0;
            have_last  <= 1'b0;
            cnt_ok     <= 32'd0;
            refused    <= 32'd0;
            c_bad      <= 16'd0;
            c_short    <= 16'd0;
            c_long     <= 16'd0;
            c_rep      <= 16'd0;
            c_ooo      <= 16'd0;
            c_err      <= 16'd0;
            scratch[1] <= 32'd0;
            scratch[2] <= 32'd0;
            scratch[3] <= 32'd0;
            cmd_period <= 16'd0;
        end else begin
            case (state)
                S_IDLE: begin
                    if (in_wr) begin
                        if (pktlen != 8'd255) pktlen <= pktlen + 8'd1;
                        if (in_data[8]) state <= S_JUDGE;
                    end
                end
                S_JUDGE: begin
                    pktlen <= 8'd0;
                    state  <= S_IDLE;
                    if (n9 < 9'd4) begin
                        c_short <= c_short + 16'd1;
                        refused <= refused + 32'd1;
                    end else if (ln > 8'd8 || n9 > lnp8) begin
                        c_long  <= c_long + 16'd1;
                        refused <= refused + 32'd1;
                    end else if (n9 < lnp8) begin
                        c_short <= c_short + 16'd1;
                        refused <= refused + 32'd1;
                    end else begin
                        crc   <= 32'hFFFFFFFF;
                        ci    <= 4'd0;
                        state <= S_CRC;
                    end
                end
                S_CRC: begin
                    crc <= crc_nx;
                    ci  <= ci + 4'd1;
                    if ({1'b0, ci} + 5'd1 == ln4) state <= S_CMP;
                end
                S_CMP: begin
                    if (~crc != trailer) begin
                        c_bad   <= c_bad + 16'd1;
                        refused <= refused + 32'd1;
                        state   <= S_IDLE;
                    end else begin
                        state <= S_EXEC;
                    end
                end
                S_EXEC: begin
                    state <= S_IDLE;
                    if (!unk && !badlen && seq_new) begin
                        last      <= seq;
                        have_last <= 1'b1;
                    end
                    case (status)
                        3'd0: begin
                            cnt_ok <= cnt_ok + 32'd1;
                            if (typ == 8'd2) scratch[r[1:0]] <= wval;
                            if (typ == 8'd4) begin
                                cmd_start  <= 1'b1;
                                cmd_period <= {pbuf[4], pbuf[5]};
                            end
                            if (typ == 8'd5) cmd_stop <= 1'b1;
                        end
                        3'd4: begin
                            if (seq_d == 16'd0) c_rep <= c_rep + 16'd1;
                            else                c_ooo <= c_ooo + 16'd1;
                            refused <= refused + 32'd1;
                        end
                        default: begin
                            c_err   <= c_err + 16'd1;
                            refused <= refused + 32'd1;
                        end
                    endcase
                end
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
